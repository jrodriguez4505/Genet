from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .adapters import Brief, ModelAdapter
from .errors import InvariantError
from .models import Artifact

SYSTEM = """You are a Worker behind Genet.
You do not command. You do not change Who. You do not spawn.
Return ONLY a JSON object with keys:
  claim (string),
  evidence (array of strings),
  uncertainty (string),
  channel_id (string),
  delta_to_picture (string),
  requests (array of strings)
No markdown. No extra keys. No authority language.
"""


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
    except json.JSONDecodeError as e:
        raise InvariantError("SCHEMA", f"model JSON invalid: {e}") from e
    if not isinstance(data, dict):
        raise InvariantError("SCHEMA", "model JSON is not an object")
    return data


def artifact_from_model(data: dict[str, Any], brief: Brief) -> Artifact:
    forbidden = {"who", "write_who", "spawn", "slots", "complete", "halt"}
    allowed = {
        "claim", "evidence", "uncertainty", "channel_id", "delta_to_picture", "requests",
    }
    extra = set(data.keys()) - allowed
    if extra & forbidden:
        raise InvariantError("WHO", "model tried to speak Who — rejected")
    extra = extra - forbidden
    if extra:
        raise InvariantError("SCHEMA", f"unknown artifact keys: {sorted(extra)}")
    claim = str(data.get("claim", "")).strip()
    if not claim:
        raise InvariantError("SCHEMA", "model artifact missing claim")
    channel = str(data.get("channel_id") or brief.channel_id or brief.skill or "execute")
    evidence = data.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    requests = data.get("requests") or []
    if isinstance(requests, str):
        requests = [requests]
    art = Artifact(
        claim=claim,
        evidence=[str(x) for x in evidence],
        uncertainty=str(data.get("uncertainty") or "unspecified"),
        channel_id=channel,
        delta_to_picture=str(data.get("delta_to_picture") or ""),
        requests=[str(x) for x in requests],
    )
    art.validate()
    return art


class LiveAdapter(ModelAdapter):
    name = "live"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "LiveAdapter":
        base = os.environ.get("TASKORG_MODEL_BASE", "").strip()
        key = os.environ.get("TASKORG_MODEL_KEY", "").strip()
        model = os.environ.get("TASKORG_MODEL_NAME", "gpt-4.1-mini").strip()
        if not base or not key:
            raise InvariantError(
                "LIVE",
                "set TASKORG_MODEL_BASE and TASKORG_MODEL_KEY for the live adapter",
            )
        timeout = int(os.environ.get("TASKORG_MODEL_TIMEOUT", "30"))
        return cls(base, key, model, timeout=timeout)

    def _payload(self, brief: Brief) -> dict:
        user = {
            "function": brief.slot_function,
            "skill": brief.skill,
            "channel_id": brief.channel_id,
            "effect": brief.effect,
            "purpose": brief.purpose,
            "picture": brief.picture,
            "end_state": brief.end_state,
            "packet": brief.packet,
            "isolated": brief.isolated,
            "success_criteria": list(brief.success_criteria or []),
        }
        return {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(user)},
            ],
        }

    def _post(self, payload: dict) -> str:
        url = self.base_url + "/chat/completions"
        raw = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=raw,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise InvariantError("LIVE", f"model endpoint failed: {e}") from e
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise InvariantError("LIVE", "unexpected model response shape") from e
        usage = body.get("usage") or {}
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
    name = "scripted"

    def __init__(self, replies: list[str]):
        self.replies = list(replies)

    def act(self, brief: Brief) -> Artifact:
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
    raise InvariantError("LIVE", f"unknown adapter: {name}")
