"""Claude through Anthropic's Messages API, with the official SDK: pip install 'taskorg[anthropic]'.

The prompts, the JSON gate and the token accounting are the live adapter's; only the transport
differs. The key comes from TASKORG_ANTHROPIC_KEY and nowhere else, so a key exported for another
tool (ANTHROPIC_API_KEY, a saved profile) is never spent by accident, and an endpoint set for the
live adapter (TASKORG_MODEL_BASE) never receives this key.
"""

from __future__ import annotations

import math
import os

from .adapters import Brief
from .errors import InvariantError
from .live import LiveAdapter, _count, env_models, env_timeout, message_text, system_prompt, user_blocks, user_message
from .tools import RUNNABLE

BASE_URL = "https://api.anthropic.com"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# The Messages API needs a reply cap. A run that sets no per-call cap gets this one.
DEFAULT_MAX_REPLY = 4096
# Past about 21,000 the SDK refuses a request that is not streamed; replies here run a few hundred tokens.
MAX_REPLY_CEILING = 16_000
# Claude counts more tokens than four characters a token: on the Haiku 5.5 pilot, 1.39 to 1.73 times that
# estimate, median 1.52. The size check before a call must not undercount, so it takes the top, rounded up.
TOKEN_RATIO = 1.75


def _sdk():
    try:
        import anthropic
    except ImportError:
        raise InvariantError("LIVE", "the anthropic adapter needs the SDK: pip install 'taskorg[anthropic]'") from None
    return anthropic


def _describe(e: Exception) -> str:
    """An SDK or network error as one line. None of them carries the key."""
    if "Timeout" in type(e).__name__:
        return "Anthropic API too slow: the response did not finish within the timeout"
    status = getattr(e, "status_code", None)
    if isinstance(status, int):
        return f"Anthropic API returned {status}: {str(getattr(e, 'message', e))[:300]}"
    return f"Anthropic API call failed: {type(e).__name__}: {str(e)[:300]}"


class AnthropicAdapter(LiveAdapter):
    """Claude's Messages API. Fills artifacts only."""

    name = "anthropic"
    token_ratio = TOKEN_RATIO
    # A sub-agent's reply after reading, on Haiku 5.5 at effort low: the 90th percentile ran 1,352 to 1,609 at
    # caps from 4,000 to 200,000 tokens, so it does not follow the cap (docs/LIVE_TESTS.md).
    part_reply_tokens = 1_500
    # A lead's reply once told a round was cut, on Haiku 5.5 at effort low, thinking included. Left under 2,500 tokens, 14
    # of 15 ran out of room, some with no visible text at all, against 1 of 9 with as little room and no cut. With 3,000
    # or more none of 729 did, and the largest took 2,416 (docs/LIVE_TESTS.md).
    round_reply_tokens = 3_000

    def __init__(self, api_key: str, model: str, timeout: int = 60, models: dict[str, str] | None = None,
                 effort: str | None = None, base_url: str = BASE_URL, client=None, cache: bool = False):
        if effort is not None and effort not in EFFORTS:
            raise InvariantError("LIVE", f"TASKORG_MODEL_EFFORT must be one of {', '.join(EFFORTS)}, got {effort!r}")
        # The SDK client holds the key; the adapter keeps none.
        super().__init__(base_url, "", model, timeout=timeout, models=models, max_reply_param="max_tokens")
        self.effort = effort
        # Prompt caching for calls that may go on to tool rounds: each round re-sends what came before it, which a
        # cache serves at a tenth of the price. Off by default: it changes the requests, so older tapes replay without.
        self.cache = bool(cache)
        if client is None:
            sdk = _sdk()
            # The key is passed in, so the SDK reads no credential from the environment. A model API
            # answers and does not redirect, so redirects are not followed.
            client = sdk.Anthropic(api_key=api_key, base_url=self.base_url, timeout=timeout,
                                   http_client=sdk.DefaultHttpxClient(follow_redirects=False))
        self._client = client

    @classmethod
    def from_env(cls) -> "AnthropicAdapter":
        key = os.environ.get("TASKORG_ANTHROPIC_KEY", "").strip()
        model = os.environ.get("TASKORG_MODEL_NAME", "").strip()
        if not key or not model:
            raise InvariantError("LIVE", "set TASKORG_ANTHROPIC_KEY and TASKORG_MODEL_NAME for the anthropic adapter")
        effort = os.environ.get("TASKORG_MODEL_EFFORT", "").strip().lower() or None
        base = os.environ.get("TASKORG_ANTHROPIC_BASE", "").strip() or BASE_URL
        cache = os.environ.get("TASKORG_MODEL_CACHE", "").strip().lower() in ("1", "on", "yes", "true")
        return cls(key, model, timeout=env_timeout(60), models=env_models(), effort=effort, base_url=base, cache=cache)

    def tape_header(self) -> dict:
        return super().tape_header() | {"effort": self.effort, "round_reply_tokens": self.round_reply_tokens,
                                        **({"cache": True} if self.cache else {})}

    def _payload(self, brief: Brief) -> dict:
        payload = {
            "model": self.model_for(brief),
            "max_tokens": max(1, min(int(brief.max_reply_tokens or DEFAULT_MAX_REPLY), MAX_REPLY_CEILING)),
            # No temperature: current Claude models reject one.
            "system": system_prompt(brief),
            "messages": [{"role": "user", "content": user_message(brief)}],
        }
        if self.effort:
            payload["output_config"] = {"effort": self.effort}
        if self.cache and any(t in RUNNABLE for t in (brief.tools or [])):
            # The same text in blocks, the newest round marked: the next round reads everything up to it from the cache.
            blocks = [{"type": "text", "text": t} for t in user_blocks(brief)]
            blocks[-2]["cache_control"] = {"type": "ephemeral"}
            payload["messages"] = [{"role": "user", "content": blocks}]
        return payload

    def estimate_tokens(self, brief: Brief) -> int:
        payload = self._payload(brief)
        chars = len(payload["system"]) + sum(len(message_text(m["content"])) for m in payload["messages"])
        return math.ceil((max(1, -(-chars // 4)) + 8) * self.token_ratio)

    def _post(self, payload: dict) -> str:
        try:
            msg = self._client.messages.create(**payload)
        except InvariantError:
            raise
        except Exception as e:  # the SDK's errors and the network's, which the SDK wraps
            raise InvariantError("LIVE", _describe(e)) from e
        blocks = getattr(msg, "content", None) or []
        # Thinking blocks come back empty; the product is the text.
        text = "".join(b.text for b in blocks if getattr(b, "type", "") == "text" and isinstance(getattr(b, "text", None), str))
        usage = getattr(msg, "usage", None)
        p, c = getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)
        if _count(p) and _count(c):
            cached = [getattr(usage, f, None) for f in ("cache_creation_input_tokens", "cache_read_input_tokens")]
            self.last_usage = {"prompt_tokens": p + sum(x for x in cached if _count(x)), "completion_tokens": c}
            # Priced apart: a cache write at 1.25 times the input price, a read at a tenth.
            for key, n in zip(("cache_write_tokens", "cache_read_tokens"), cached):
                if _count(n) and n:
                    self.last_usage[key] = n
            thinking = getattr(getattr(usage, "output_tokens_details", None), "thinking_tokens", None)
            if _count(thinking):
                self.last_usage["thinking_tokens"] = thinking  # part of completion_tokens, for the record
        else:
            sent = len(payload["system"]) + sum(len(message_text(m["content"])) for m in payload["messages"])
            self.last_usage = {
                "prompt_tokens": p if _count(p) else max(1, -(-sent // 4)) + 8,
                "completion_tokens": c if _count(c) else max(1, -(-len(text) // 4)),
                "estimated": True,
            }
        if getattr(msg, "stop_reason", None) == "refusal":
            category = getattr(getattr(msg, "stop_details", None), "category", None)
            raise InvariantError("LIVE", "the model declined the request" + (f" ({category})" if category else ""))
        return text
