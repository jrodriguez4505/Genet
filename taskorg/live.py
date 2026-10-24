from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .adapters import Brief, ModelAdapter
from .errors import InvariantError
from .models import SKILLS, Artifact
from .skills import brief as skill_brief
from .tools import RUNNABLE

ROLES = {
    "lead": (
        "You are the lead agent of a small team. You hold the goal, purpose and done-when condition. "
        "When a single agent is enough you do the work yourself. When sub-agents report, you merge "
        "their results against the goal and do not invent what they did not report."
    ),
    "worker": (
        "You are one sub-agent of a small team, working channel {channel}. Work only your channel. "
        "You cannot see the other sub-agents and must not guess at their work."
    ),
    "verifier": (
        "You are the verifier. Judge the product, not the plan. Your claim starts with PASS or FAIL. "
        "PASS only if the product itself meets every success criterion."
    ),
}

SYSTEM = """{role}
Your skill right now: {skill}. {skill_brief}
You do not command. You do not change the roster. You do not spawn.
{tools}
Return ONLY a JSON object with keys:
  claim (string),
  evidence (array of strings),
  uncertainty (string),
  channel_id (string),
  context_update (string),
  requests (array of strings)
No markdown. No extra keys. No authority language.
"""

TOOLS_ON = (
    "Tools you may use: {names}. To use one, put requests such as {examples} in requests and make "
    "claim a short interim note. The results come back in the packet under TOOL RESULTS. "
    "When you have what you need, return the product with requests empty."
)
TOOLS_OFF = "You have no tools. Leave requests empty unless the brief asks for proposals."
_EXAMPLES = {"read": '"read:notes/a.md"', "retrieve": '"retrieve:quarterly revenue"', "observe": '"observe"'}

# The endpoint's reply is untrusted input. A chat completion is kilobytes; this is generous.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
ERROR_DETAIL_BYTES = 2048
CHUNK = 64 * 1024
TIMEOUT_RANGE = (1, 3600)  # seconds; a call that may not wait at all, or forever, is a typo


def _is_loopback(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_base_url(base_url: str) -> str:
    """https, or plain http only to this machine (a local model server), so the key never crosses
    a network in clear text. TASKORG_MODEL_ALLOW_HTTP=1 allows plain http elsewhere, such as a LAN server."""
    try:
        if any(c <= " " or c == "\x7f" for c in base_url):
            raise ValueError("spaces or control characters")
        parts = urllib.parse.urlsplit(base_url)
        host = (parts.hostname or "").lower()
        parts.port  # raises ValueError on a port that is not a number
    except ValueError as e:
        raise InvariantError("LIVE", f"model base URL is not a valid URL: {e}") from None
    if host and parts.scheme == "https":
        return base_url
    if host and parts.scheme == "http" and (_is_loopback(host) or os.environ.get("TASKORG_MODEL_ALLOW_HTTP") == "1"):
        return base_url
    # Scheme and host only: the URL itself may carry credentials.
    raise InvariantError(
        "LIVE", f"model base URL must be https:// (or http:// to this machine), got {parts.scheme or '?'}://{host or '?'}"
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A model API answers; it does not redirect. Following one would carry the request, and with
    some redirects the key, to a host the operator never named."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _deadline_connection(base, req):
    """A connection that shuts its socket at the request's deadline, whatever phase it is in:
    the handshake, the status line and headers, or a body. A server cannot hold a call open
    by sending a byte at a time."""

    class Connection(base):
        def connect(self):
            timer = threading.Timer(max(0.0, req.deadline - time.monotonic()), self._expire)
            timer.daemon = True
            req.timers.append(timer)
            timer.start()
            super().connect()
            self._raw = self.sock

        def _expire(self):
            sock = getattr(self, "_raw", None) or self.sock
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    return Connection


class _DeadlineHTTP(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_deadline_connection(http.client.HTTPConnection, req), req)


class _DeadlineHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req):
        kw = {"context": self._context}
        if hasattr(self, "_check_hostname"):  # Python 3.11
            kw["check_hostname"] = self._check_hostname
        return self.do_open(_deadline_connection(http.client.HTTPSConnection, req), req, **kw)


_OPENER = urllib.request.build_opener(_NoRedirect, _DeadlineHTTP, _DeadlineHTTPS)


def _read_capped(resp, limit: int, deadline: float) -> bytes:
    """The body, refused past limit bytes or past the deadline, so an endpoint cannot exhaust memory or stall a run."""
    read = getattr(resp, "read1", resp.read)
    chunks, total = [], 0
    while True:
        if time.monotonic() > deadline:
            raise InvariantError("LIVE", "model endpoint too slow: the response did not finish within the timeout")
        chunk = read(CHUNK)
        if not chunk:
            if time.monotonic() > deadline:  # the deadline shut the socket mid-body
                raise InvariantError("LIVE", "model endpoint too slow: the response did not finish within the timeout")
            return b"".join(chunks)
        total += len(chunk)
        if total > limit:
            raise InvariantError("LIVE", f"model endpoint response is over {limit} bytes; refused")
        chunks.append(chunk)


def system_prompt(brief: Brief) -> str:
    runnable = [t for t in (brief.tools or []) if t in RUNNABLE]
    tools = (
        TOOLS_ON.format(names=", ".join(runnable), examples=", ".join(_EXAMPLES[t] for t in runnable))
        if runnable
        else TOOLS_OFF
    )
    role = ROLES.get(brief.slot_function, ROLES["worker"]).format(channel=brief.channel_id or "?")
    return SYSTEM.format(role=role, skill=brief.skill, skill_brief=skill_brief(brief.skill), tools=tools)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise InvariantError("SCHEMA", "model returned no JSON object")
    try:
        data = json.loads(text[start : end + 1])
    except (ValueError, RecursionError) as e:  # bad JSON, a number too long to convert, or nesting too deep
        raise InvariantError("SCHEMA", f"model JSON invalid: {type(e).__name__}: {str(e)[:120]}") from e
    if not isinstance(data, dict):
        raise InvariantError("SCHEMA", "model JSON is not an object")
    return data


def artifact_from_model(data: dict[str, Any], brief: Brief) -> Artifact:
    forbidden = {"roster", "set_roster", "spawn", "slots", "complete", "halt"}
    allowed = {
        "claim",
        "evidence",
        "uncertainty",
        "channel_id",
        "context_update",
        "requests",
    }
    extra = set(data.keys()) - allowed
    if extra & forbidden:
        raise InvariantError("ROSTER", "model tried to change the roster; rejected")
    extra = extra - forbidden
    if extra:
        raise InvariantError("SCHEMA", f"unknown artifact keys: {sorted(extra)}")
    claim = data.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        raise InvariantError("SCHEMA", "model artifact missing claim: it must be a non-empty string")
    claim = claim.strip()
    channel = str(data.get("channel_id") or brief.channel_id or brief.skill or "execute")
    evidence = data.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = [evidence]
    requests = data.get("requests") or []
    if not isinstance(requests, list):
        requests = [requests]
    art = Artifact(
        claim=claim,
        evidence=[str(x) for x in evidence],
        uncertainty=str(data.get("uncertainty") or "unspecified"),
        channel_id=channel,
        context_update=str(data.get("context_update") or ""),
        requests=[str(x) for x in requests],
    )
    art.validate()
    return art


class LiveAdapter(ModelAdapter):
    """OpenAI-compatible chat adapter. Fills artifacts only."""

    name = "live"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60, models: dict[str, str] | None = None):
        self.base_url = check_base_url(base_url).rstrip("/")
        self.api_key = api_key
        self.model = model
        # Optional model per skill, e.g. a stronger model for reason.
        self.models = dict(models or {})
        self.timeout = timeout
        self._local = threading.local()

    @property
    def last_usage(self) -> dict:
        """Per thread: sub-agents call the model concurrently."""
        return getattr(self._local, "usage", {})

    @last_usage.setter
    def last_usage(self, usage: dict) -> None:
        self._local.usage = usage

    def model_for(self, brief: Brief) -> str:
        return self.models.get(brief.skill) or self.model

    @classmethod
    def from_env(cls) -> "LiveAdapter":
        base = os.environ.get("TASKORG_MODEL_BASE", "").strip()
        key = os.environ.get("TASKORG_MODEL_KEY", "").strip()
        # An exported-but-empty name must not reach the endpoint as "".
        model = os.environ.get("TASKORG_MODEL_NAME", "").strip()
        if not base or not key or not model:
            raise InvariantError(
                "LIVE",
                "set TASKORG_MODEL_BASE, TASKORG_MODEL_KEY and TASKORG_MODEL_NAME for the live adapter",
            )
        raw_timeout = os.environ.get("TASKORG_MODEL_TIMEOUT", "").strip() or "30"
        try:
            timeout = int(raw_timeout)
        except ValueError as e:
            raise InvariantError("LIVE", f"TASKORG_MODEL_TIMEOUT must be whole seconds, got {raw_timeout!r}") from e
        lo, hi = TIMEOUT_RANGE
        if not lo <= timeout <= hi:
            raise InvariantError("LIVE", f"TASKORG_MODEL_TIMEOUT must be {lo} to {hi} seconds, got {timeout}")
        models = {
            q: os.environ[f"TASKORG_MODEL_NAME_{q.upper()}"].strip()
            for q in SKILLS
            if os.environ.get(f"TASKORG_MODEL_NAME_{q.upper()}", "").strip()
        }
        return cls(base, key, model, timeout=timeout, models=models)

    def _payload(self, brief: Brief) -> dict:
        user = {
            "function": brief.slot_function,
            "skill": brief.skill,
            "channel_id": brief.channel_id,
            "goal": brief.goal,
            "purpose": brief.purpose,
            "context": brief.context,
            "done_when": brief.done_when,
            "packet": brief.packet,
            "isolated": brief.isolated,
            "mode": brief.mode,
            "tools": list(brief.tools or []),
            "success_criteria": list(brief.success_criteria or []),
        }
        return {
            "model": self.model_for(brief),
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt(brief)},
                {"role": "user", "content": json.dumps(user)},
            ],
        }

    def estimate_tokens(self, brief: Brief) -> int:
        """What is actually sent: the system prompt and the JSON user message, not only the brief's text."""
        chars = sum(len(m["content"]) for m in self._payload(brief)["messages"])
        return max(1, -(-chars // 4)) + 8  # plus message framing

    def _post(self, payload: dict) -> str:
        url = self.base_url + "/chat/completions"
        raw = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST")
        # Never copied onto a redirected request.
        req.add_unredirected_header("Authorization", f"Bearer {self.api_key}")
        # One deadline for the whole exchange; _deadline_connection enforces it.
        req.deadline, req.timers = time.monotonic() + self.timeout, []
        try:
            with _OPENER.open(req, timeout=self.timeout) as resp:
                data = _read_capped(resp, MAX_RESPONSE_BYTES, req.deadline)
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400:
                raise InvariantError("LIVE", f"model endpoint redirected ({e.code}); redirects are not followed") from e
            try:
                detail = e.read(ERROR_DETAIL_BYTES).decode("utf-8", errors="replace")[:300]
            except (OSError, http.client.HTTPException, ValueError):
                detail = ""
            raise InvariantError("LIVE", f"model endpoint returned {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, ValueError) as e:
            if time.monotonic() >= req.deadline:
                raise InvariantError("LIVE", "model endpoint too slow: the response did not finish within the timeout") from e
            raise InvariantError("LIVE", f"model endpoint failed: {type(e).__name__}: {e}") from e
        finally:
            for timer in req.timers:
                timer.cancel()
        try:
            body = json.loads(data.decode("utf-8"))
        except (ValueError, RecursionError) as e:  # includes UnicodeDecodeError and over-long numbers
            raise InvariantError("LIVE", f"model endpoint returned non-JSON: {type(e).__name__}: {str(e)[:120]}") from e
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise InvariantError("LIVE", "unexpected model response shape") from e
        if not isinstance(content, str):
            raise InvariantError("LIVE", "model returned no text content")
        usage = body.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        self.last_usage = {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        }
        return content

    def act(self, brief: Brief) -> Artifact:
        self.last_usage = {}
        text = self._post(self._payload(brief))
        data = _extract_json(text)
        return artifact_from_model(data, brief)


class ScriptedLive(ModelAdapter):
    """Test double: pretends to be a model. Still must pass the JSON gate."""

    name = "scripted"

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self._lock = threading.Lock()

    def act(self, brief: Brief) -> Artifact:
        with self._lock:
            if not self.replies:
                raise InvariantError("LIVE", "scripted adapter exhausted")
            text = self.replies.pop(0)
        return artifact_from_model(_extract_json(text), brief)


def pick_adapter(name: str) -> ModelAdapter:
    if name == "stub":
        from .adapters import StubAdapter

        return StubAdapter()
    if name == "live":
        return LiveAdapter.from_env()
    if name == "sim":
        from .sim import SimModel

        return SimModel()
    raise InvariantError("LIVE", f"unknown adapter: {name}")
