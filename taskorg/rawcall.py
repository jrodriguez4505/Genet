"""Messages API calls made outside Genet's own briefs, counted, capped and taped the way the adapter's are.

The head-to-head (docs/HEAD_TO_HEAD.md) sends two kinds of request that are not a Genet brief: the judge's,
and every request CrewAI makes. RawClient stands where the Anthropic SDK client would, with the same
`messages.create(**params)`, so CrewAI's own Anthropic provider runs unchanged on top of it. Every call:

  - is sized first, four characters a token times the adapter's TOKEN_RATIO, and refused past the per-call
    limit with words CrewAI reads as a full context, so CrewAI handles it its own way (it summarises);
  - has its reply capped to what is left of that limit, as Genet's calls do;
  - counts against the trial's calls, tokens and seconds, and stops the trial past any of them;
  - counts against a dollar cap across trials;
  - is saved whole, request and response, to a tape that replays it with no key.

The key comes from TASKORG_ANTHROPIC_KEY and nowhere else, as the adapter's does, so an SDK or framework that
looks for ANTHROPIC_API_KEY finds nothing to spend.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import math
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from .anthropic_live import BASE_URL, MAX_REPLY_CEILING, TOKEN_RATIO, _describe, _sdk
from .errors import InvariantError

RAW_FORMAT = 1
# What the reply needs at least; less room than this is a full context.
MIN_REPLY = 1_500
# Settings current Claude models reject, and Genet never sends: dropped so both sides send the same kind of request.
DROPPED = ("temperature", "top_p", "top_k")
# Which agent made the call, set by whoever calls (CrewAI's LLM wrapper), for the record.
current_agent: contextvars.ContextVar[str] = contextvars.ContextVar("current_agent", default="")


class ContextFull(InvariantError):
    """A request past the per-call limit. The words are the ones CrewAI reads as a full context window."""

    def __init__(self, estimate: int, limit: int):
        super().__init__("BUDGET", f"maximum context length exceeded: about {estimate:,} tokens with room for the "
                                   f"reply, against a call limit of {limit:,}")


def request_key(params: dict) -> str:
    """The request without its reply cap, as tape.request_key does: the cap follows the budget."""
    body = {k: v for k, v in params.items() if k != "max_tokens"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def estimate_tokens(params: dict) -> int:
    """Everything the model reads: system, messages (text, tool calls, tool results) and tool definitions."""
    chars = len(json.dumps(params.get("system") or "", ensure_ascii=False))
    chars += len(json.dumps(params.get("messages") or [], ensure_ascii=False))
    chars += len(json.dumps(params.get("tools") or [], ensure_ascii=False))
    return math.ceil((max(1, -(-chars // 4)) + 8) * TOKEN_RATIO)


class RawTape:
    """Writes each exchange as it ends. Never writes over a tape: it is the record of what was spent."""

    def __init__(self, path: str | Path, header: dict):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._file = self.path.open("x", encoding="utf-8")
        except FileExistsError:
            raise InvariantError("COMPARE", f"tape {self.path} already exists; name a new one") from None
        self._lock = threading.Lock()
        self.count = 0
        self._write({"raw_tape": RAW_FORMAT, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")} | header)

    def _write(self, entry: dict) -> None:
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()

    def add(self, entry: dict) -> None:
        self._write(entry)
        with self._lock:
            self.count += 1

    def close(self) -> None:
        with self._lock:
            self._file.close()


class RawPlayer:
    """Serves a raw tape's responses for the same requests, in order, then the last again."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._replies: dict[str, list[dict]] = {}
        self._served: dict[str, int] = {}
        self.misses = self.served = 0
        with self.path.open(encoding="utf-8") as fh:
            lines = [ln for ln in fh if ln.strip()]
        if not lines:
            raise InvariantError("COMPARE", f"tape {self.path} is empty")
        self.header = json.loads(lines[0])
        if self.header.get("raw_tape") != RAW_FORMAT:
            raise InvariantError("COMPARE", f"{self.path} is not a raw tape of format {RAW_FORMAT}")
        for n, line in enumerate(lines[1:], 2):
            e = json.loads(line)
            if not isinstance(e, dict) or "key" not in e:
                raise InvariantError("COMPARE", f"tape {self.path} line {n} is not a recorded exchange")
            self._replies.setdefault(e["key"], []).append(e)

    def take(self, key: str) -> dict | None:
        with self._lock:
            entries = self._replies.get(key)
            if not entries:
                self.misses += 1
                return None
            i = self._served.get(key, 0)
            self._served[key] = i + 1
            self.served += 1
            return entries[min(i, len(entries) - 1)]


class Spend:
    """Tokens the calls that went to the model used, across trials, priced per model."""

    def __init__(self, prices: dict[str, tuple[float, float]] | None = None, default: tuple[float, float] = (0.0, 0.0)):
        self._lock = threading.Lock()
        self.prices, self.default = dict(prices or {}), default
        self.calls, self.dollars = 0, 0.0

    def add(self, model: str, usage: dict) -> None:
        pin, pout = self.prices.get(model, self.default)
        p, c = usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
        write, read = usage.get("cache_write_tokens") or 0, usage.get("cache_read_tokens") or 0
        cost = ((p - write - read) * pin + write * pin * 1.25 + read * pin * 0.1 + c * pout) / 1e6
        with self._lock:
            self.calls += 1
            self.dollars += cost


class _Trial:
    def __init__(self, max_calls: int, max_tokens: int, max_seconds: float):
        self.max_calls, self.max_tokens, self.max_seconds = max_calls, max_tokens, max_seconds
        self.started = time.perf_counter()
        self.calls: list[dict] = []
        self.stopped = ""

    def check(self) -> None:
        if len(self.calls) >= self.max_calls:
            self.stopped = f"the trial's {self.max_calls} calls are used"
        elif sum(c["prompt_tokens"] + c["completion_tokens"] for c in self.calls) >= self.max_tokens:
            self.stopped = f"the trial's {self.max_tokens:,} tokens are used"
        elif time.perf_counter() - self.started > self.max_seconds:
            self.stopped = f"the trial ran past {self.max_seconds:g} seconds"
        if self.stopped:
            raise InvariantError("BUDGET", self.stopped)


def _usage(msg) -> dict:
    u = getattr(msg, "usage", None)
    write = getattr(u, "cache_creation_input_tokens", None) or 0
    read = getattr(u, "cache_read_input_tokens", None) or 0
    out = {"prompt_tokens": (getattr(u, "input_tokens", None) or 0) + write + read,
           "completion_tokens": getattr(u, "output_tokens", None) or 0}
    if write:
        out["cache_write_tokens"] = write
    if read:
        out["cache_read_tokens"] = read
    return out


class _Messages:
    def __init__(self, client: "RawClient"):
        self._client = client

    def create(self, **params):
        return self._client.create(**params)

    def count_tokens(self, **params):
        """Counted here, not by the API: a count is a request too, and this one costs nothing."""
        return SimpleNamespace(input_tokens=estimate_tokens(params))


class RawClient:
    """In place of anthropic.Anthropic for one model setup: messages.create(**params) returns the SDK's Message."""

    def __init__(self, *, call_limit: int, sdk_client=None, tape: RawTape | None = None, player: RawPlayer | None = None,
                 spend: Spend | None = None, max_spend: float | None = None, effort: str | None = "low"):
        if (sdk_client is None) == (player is None):
            raise ValueError("a raw client needs either an SDK client or a tape to replay, not both")
        self.call_limit, self.sdk, self.tape, self.player = call_limit, sdk_client, tape, player
        self.spend, self.max_spend, self.effort = spend or Spend(), max_spend, effort
        self.messages = _Messages(self)
        self.beta = SimpleNamespace(messages=self.messages)
        self._trial: _Trial | None = None
        self._lock = threading.Lock()

    @classmethod
    def live(cls, *, call_limit: int, timeout: int = 120, **kwargs) -> "RawClient":
        key = os.environ.get("TASKORG_ANTHROPIC_KEY", "").strip()
        if not key:
            raise InvariantError("LIVE", "set TASKORG_ANTHROPIC_KEY for live calls")
        sdk = _sdk()
        base = os.environ.get("TASKORG_ANTHROPIC_BASE", "").strip() or BASE_URL
        client = sdk.Anthropic(api_key=key, base_url=base, timeout=timeout, max_retries=2,
                               http_client=sdk.DefaultHttpxClient(follow_redirects=False))
        return cls(call_limit=call_limit, sdk_client=client, **kwargs)

    # --- a trial ---

    def begin_trial(self, max_calls: int, max_tokens: int, max_seconds: float) -> None:
        with self._lock:
            self._trial = _Trial(max_calls, max_tokens, max_seconds)

    def end_trial(self) -> dict:
        with self._lock:
            t, self._trial = self._trial, None
        calls = t.calls if t else []
        return {"calls": calls, "stopped": t.stopped if t else "",
                "seconds": round(time.perf_counter() - t.started, 3) if t else 0.0}

    # --- a call ---

    def prepare(self, params: dict) -> dict:
        """The request as it is sent: no stream, no sampling settings, Genet's effort, a reply cap inside the limit."""
        params = {k: v for k, v in params.items() if k not in DROPPED and k != "stream"}
        if self.effort and "output_config" not in params:
            params["output_config"] = {"effort": self.effort}
        est = estimate_tokens(params)
        room = self.call_limit - est
        if room < MIN_REPLY:
            raise ContextFull(est + MIN_REPLY, self.call_limit)
        params["max_tokens"] = max(1, min(int(params.get("max_tokens") or 4096), room, MAX_REPLY_CEILING))
        return params

    def create(self, **params):
        params = self.prepare(params)
        with self._lock:
            trial = self._trial
            if trial:
                trial.check()
            if self.max_spend is not None and self.spend.dollars >= self.max_spend:
                raise InvariantError("BUDGET", f"the ${self.max_spend:.2f} spend cap is reached")
            if trial:  # held before the call, so calls running side by side cannot all pass the last check
                trial.calls.append({"prompt_tokens": 0, "completion_tokens": 0, "pending": True})
                slot = trial.calls[-1]
        key, model, agent = request_key(params), params.get("model", ""), current_agent.get()
        started = time.perf_counter()
        try:
            msg, usage = self._send(key, params)
        except InvariantError as e:
            if self.tape and self.player is None:
                self.tape.add({"key": key, "request": params, "response": None, "usage": {}, "agent": agent,
                               "error": {"code": e.code, "message": e.message},
                               "latency_s": round(time.perf_counter() - started, 3)})
            if trial:
                slot.update(pending=False, error=e.code, agent=agent, model=model)
            raise
        if self.tape and self.player is None:
            self.tape.add({"key": key, "request": params, "response": msg.model_dump(mode="json"), "usage": usage,
                           "agent": agent, "error": None, "latency_s": round(time.perf_counter() - started, 3)})
        if self.player is None:
            self.spend.add(model, usage)
        if trial:
            slot.update(usage, pending=False, agent=agent, model=model)
        return msg

    def _send(self, key: str, params: dict):
        if self.player is not None:
            entry = self.player.take(key)
            if entry is None:
                raise InvariantError("LIVE", "replay: the tape has no reply for this request")
            if entry.get("error"):
                raise InvariantError(entry["error"]["code"], entry["error"]["message"])
            return _sdk().types.Message.model_validate(entry["response"]), dict(entry.get("usage") or {})
        try:
            msg = self.sdk.messages.create(**params)
        except Exception as e:  # the SDK's errors and the network's
            raise InvariantError("LIVE", _describe(e)) from e
        if getattr(msg, "stop_reason", None) == "refusal":
            raise InvariantError("LIVE", "the model declined the request")
        return msg, _usage(msg)
