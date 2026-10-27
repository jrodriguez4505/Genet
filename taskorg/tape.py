"""A tape: every exchange with a live model, saved as it happens, so a run can be replayed later
with no key and no spend.

The tape is JSON lines. The first line describes the adapter, never its key or base URL. Each
later line is one request and what came back: the reply text and its usage, or the error. A replay
serves the recorded reply for the same request, so the kernel, the gates and the grading can be
refined against real replies. A request the tape never saw, because a prompt or brief changed
since, fails as LIVE and is counted, so a refinement shows where it left the recording.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

from .errors import InvariantError

FORMAT = 1
ADAPTERS = ("live", "anthropic")
# What _post may raise; the parse that follows a reply runs again on replay.
ERROR_CODES = ("LIVE",)
_KEY = re.compile(r"[0-9a-f]{64}")


def request_key(payload: dict, cap_field: str | None) -> str:
    """The request without its reply cap: the cap follows the run's budget; the rest is what the model reads."""
    body = {k: v for k, v in payload.items() if k != cap_field}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


class Recorder:
    """Writes each exchange the moment it ends, so a run that stops early keeps what it spent."""

    def __init__(self, path: Path, header: dict):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # A tape is the record of what was spent: never write over one.
            self._file = self.path.open("x", encoding="utf-8")
        except FileExistsError:
            raise InvariantError("COMPARE", f"tape {self.path} already exists; name a new one") from None
        self._lock = threading.Lock()
        self.count = 0
        self._write({"tape": FORMAT, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")} | header)

    def _write(self, entry: dict) -> None:
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()

    def _entry(self, key: str, payload: dict, reply: str | None, usage: dict, error: dict | None, started: float) -> None:
        self._write({"key": key, "request": payload, "reply": reply, "usage": dict(usage or {}), "error": error,
                     "latency_s": round(time.perf_counter() - started, 3)})
        with self._lock:
            self.count += 1

    def exchange(self, adapter, payload: dict) -> str:
        key = request_key(payload, adapter.max_reply_param)
        started = time.perf_counter()
        try:
            text = adapter._post(payload)
        except InvariantError as e:
            self._entry(key, payload, None, adapter.last_usage, {"code": e.code, "message": e.message}, started)
            raise
        self._entry(key, payload, text, adapter.last_usage, None, started)
        return text

    def close(self) -> None:
        with self._lock:
            self._file.close()


def _usage_ok(usage) -> bool:
    if not isinstance(usage, dict):
        return False
    counts = [v for k, v in usage.items() if k != "estimated"]
    return all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in counts) and isinstance(
        usage.get("estimated", False), bool)


class Player:
    """Serves a tape's replies by request. Identical requests get the recorded replies in order, then the last again."""

    def __init__(self, path: Path):
        self.path = Path(path)
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as e:
            raise InvariantError("COMPARE", f"cannot read tape {self.path}: {e}") from None
        if not lines:
            raise InvariantError("COMPARE", f"tape {self.path} is empty")
        self.header = self._header(self._parse(lines[0], 1))
        self._replies: dict[str, list[dict]] = {}
        for n, line in enumerate(lines[1:], 2):
            if not line.strip():
                continue
            try:
                entry = self._parse(line, n)
            except InvariantError:
                if n == len(lines):  # a run stopped mid-write leaves a partial last line
                    break
                raise
            self._replies.setdefault(self._entry(entry, n), []).append(entry)
        self._served: dict[str, int] = {}
        self._lock = threading.Lock()
        self.served = self.repeated = self.misses = 0

    def _parse(self, line: str, n: int) -> dict:
        try:
            data = json.loads(line)
        except (ValueError, RecursionError):
            raise InvariantError("COMPARE", f"tape {self.path} line {n} is not JSON") from None
        if not isinstance(data, dict):
            raise InvariantError("COMPARE", f"tape {self.path} line {n} is not an object")
        return data

    def _header(self, h: dict) -> dict:
        models = h.get("models", {})
        ok = (
            h.get("tape") == FORMAT
            and h.get("adapter") in ADAPTERS
            and isinstance(h.get("model"), str) and h["model"]
            and isinstance(models, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in models.items())
            and (h.get("effort") is None or isinstance(h["effort"], str))
            and (h.get("max_reply_param") is None or isinstance(h["max_reply_param"], str))
        )
        if not ok:
            raise InvariantError("COMPARE", f"tape {self.path} has no valid header (format {FORMAT}, adapter {' or '.join(ADAPTERS)})")
        return h

    def _entry(self, e: dict, n: int) -> str:
        error = e.get("error")
        ok = (
            isinstance(e.get("key"), str) and _KEY.fullmatch(e["key"])
            and _usage_ok(e.get("usage", {}))
            and (
                (isinstance(e.get("reply"), str) and error is None)
                or (e.get("reply") is None and isinstance(error, dict) and error.get("code") in ERROR_CODES
                    and isinstance(error.get("message"), str))
            )
        )
        if not ok:
            raise InvariantError("COMPARE", f"tape {self.path} line {n} is not a recorded exchange")
        e.setdefault("usage", {})
        return e["key"]

    def exchange(self, adapter, payload: dict) -> str:
        key = request_key(payload, adapter.max_reply_param)
        with self._lock:
            entries = self._replies.get(key)
            entry = None
            if entries:
                i = self._served.get(key, 0)
                entry = entries[min(i, len(entries) - 1)]
                self._served[key] = i + 1
                self.served += 1
                self.repeated += i >= len(entries)
            else:
                self.misses += 1
        if entry is None:
            adapter.last_usage = {}
            raise InvariantError("LIVE", "replay: the tape has no reply for this request; a prompt or brief changed since it was recorded")
        adapter.last_usage = dict(entry["usage"])
        if entry["error"]:
            raise InvariantError(entry["error"]["code"], entry["error"]["message"])
        return entry["reply"]


class _Offline:
    """The client a replayed anthropic adapter holds: replay never reaches the API."""

    class messages:  # noqa: N801 - the SDK's attribute name
        @staticmethod
        def create(**_):
            raise InvariantError("LIVE", "replay does not call the API")


def replay_adapter(player: Player):
    """The recorded adapter, built the same way so it sends the same requests, answering from the tape."""
    h = player.header
    if h["adapter"] == "anthropic":
        from .anthropic_live import AnthropicAdapter

        adapter = AnthropicAdapter("", h["model"], models=h.get("models"), effort=h.get("effort"), client=_Offline())
    else:
        from .live import LiveAdapter

        # .invalid never resolves: even a request that slipped past the tape could go nowhere.
        adapter = LiveAdapter("https://replay.invalid", "", h["model"], models=h.get("models"),
                              max_reply_param=h.get("max_reply_param"))
    adapter.name = f"replay:{h['adapter']}"
    adapter.tape = player
    return adapter
