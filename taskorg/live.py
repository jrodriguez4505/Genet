from __future__ import annotations

import json
import os
import threading
import urllib.error
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
    except json.JSONDecodeError as e:
        raise InvariantError("SCHEMA", f"model JSON invalid: {e}") from e
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
    claim = str(data.get("claim", "")).strip()
    if not claim:
        raise InvariantError("SCHEMA", "model artifact missing claim")
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
        self.base_url = base_url.rstrip("/")
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
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            raise InvariantError("LIVE", f"model endpoint returned {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise InvariantError("LIVE", f"model endpoint failed: {e}") from e
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise InvariantError("LIVE", f"model endpoint returned non-JSON: {e}") from e
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise InvariantError("LIVE", "unexpected model response shape") from e
        if not isinstance(content, str):
            raise InvariantError("LIVE", "model returned no text content")
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
