"""Policy head socket.

A net (or stub) may propose. The kernel still writes. This module has no
path to the roster writer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .errors import InvariantError
from .gates import World, decide
from .run import Run
from .models import Status

ACTIONS = (
    "HOLD",
    "INSPECT",
    "ACTIVATE_SKILL",
    "CHANGE_METHOD",
    "PROPOSE_CHANNEL",
    "REVISE_GOAL",
    "STOP",
)

FEATURE_NAMES = (
    "worker_count",
    "slot_count",
    "open_reviews",
    "context_sufficient",
    "allow_split",
    "allow_adapt",
    "remaining_calls",
    "remaining_tokens_k",
    "world_files",
    "world_channels",
    "axes_count",
    "context_chars",
    "replan_open",
    "status_active",
    "calls_used",
)


@dataclass
class BoardState:
    features: dict[str, float]
    vector: list[float]
    extras: dict = field(default_factory=dict)

    def get(self, name: str, default: float = 0.0) -> float:
        return float(self.features.get(name, default))


@dataclass
class PolicyDecision:
    action: str
    confidence: float = 1.0
    rationale_id: str = ""
    channel_id: str = ""
    named_failure: str = ""
    method: str = ""
    skill: str = ""

    def __post_init__(self):
        if self.action not in ACTIONS:
            raise InvariantError("SCHEMA", f"unknown policy action: {self.action}")
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


class PolicyHead(Protocol):
    threshold: float

    def act(self, state: BoardState) -> PolicyDecision: ...


def encode_board(run: Run) -> BoardState:
    b = getattr(run, "budget", None)
    world = getattr(run, "world", None) or World()
    calls = len(getattr(run, "calls", []) or [])
    tokens = sum(
        (c.get("prompt_tokens") or 0) + (c.get("completion_tokens") or 0)
        for c in getattr(run, "calls", []) or []
    )
    remaining_calls = float(getattr(b, "max_calls", 12) - calls) if b else 12.0
    remaining_tokens = float(getattr(b, "max_tokens", 50_000) - tokens) if b else 50_000.0
    features = {
        "worker_count": float(run.state.worker_count()),
        "slot_count": float(len(run.state.slots)),
        "open_reviews": float(len(run.open_review_ids())),
        "context_sufficient": 1.0 if run.state.context_sufficient else 0.0,
        "allow_split": 1.0 if getattr(b, "allow_split", False) else 0.0,
        "allow_adapt": 1.0 if getattr(b, "allow_adapt", False) else 0.0,
        "remaining_calls": remaining_calls,
        "remaining_tokens_k": remaining_tokens / 1000.0,
        "world_files": float(len(getattr(world, "existing_files", []) or [])),
        "world_channels": float(len(getattr(world, "existing_channels", []) or [])),
        "axes_count": float(len(run.state.axes or [])),
        "context_chars": float(len(run.state.context or "")),
        "replan_open": 1.0 if run.summary().get("replan_open") else 0.0,
        "status_active": 1.0 if run.status == Status.ACTIVE else 0.0,
        "calls_used": float(calls),
    }
    vector = [float(features[n]) for n in FEATURE_NAMES]
    extras = {
        "id": run.id,
        "goal": run.state.goal,
        "purpose": run.state.purpose,
        "method": run.state.method,
        "tier": getattr(b, "tier", ""),
        "status": run.status.value,
    }
    return BoardState(features=features, vector=vector, extras=extras)


class StubPolicy:
    """Deterministic stand-in. Reproduces the current if/else, never writes the roster."""

    threshold = 0.35
    name = "stub-policy"

    def act(self, state: BoardState) -> PolicyDecision:
        if state.get("status_active") < 1.0:
            return PolicyDecision("STOP", confidence=1.0, rationale_id="already-closed")
        if state.get("context_sufficient") < 1.0:
            return PolicyDecision("INSPECT", confidence=0.9, rationale_id="context-thin")
        if state.get("replan_open") >= 1.0:
            return PolicyDecision("CHANGE_METHOD", confidence=0.85, rationale_id="replan")
        if state.get("world_files") >= 1.0 and state.get("allow_split") < 1.0:
            return PolicyDecision("HOLD", confidence=0.8, rationale_id="exists-hold")
        return PolicyDecision("HOLD", confidence=0.7, rationale_id="default-hold")


def clamp(decision: PolicyDecision, threshold: float = 0.35) -> PolicyDecision:
    if decision.confidence < threshold:
        return PolicyDecision("HOLD", confidence=decision.confidence, rationale_id="low-confidence")
    return decision


def apply_decision(run: Run, decision: PolicyDecision) -> str:
    """Mutate only legal fields. Never call set_roster. Channel proposals hit decide()."""
    decision = clamp(decision)
    run._record(
        "policy",
        {
            "action": decision.action,
            "confidence": decision.confidence,
            "rationale_id": decision.rationale_id,
            "channel_id": decision.channel_id,
        },
    )
    if decision.action == "HOLD":
        return "held"
    if decision.action == "INSPECT":
        return "inspect"
    if decision.action == "ACTIVATE_SKILL":
        skill = decision.skill or "draft"
        lead = run.state.lead_id
        run.switch_skill(lead, lead, skill, "policy activate")
        return "activated"
    if decision.action == "CHANGE_METHOD":
        lead = run.state.lead_id
        run.set_method(lead, decision.method or "revised method", list(run.state.axes or []))
        return "method-changed"
    if decision.action == "REVISE_GOAL":
        return "revise-needs-lead"
    if decision.action == "STOP":
        return "stop-requested"
    if decision.action == "PROPOSE_CHANNEL":
        from .gates import Subtask

        if not decision.channel_id or not decision.named_failure:
            return "proposal-incomplete"
        occupied = [s.channel_id for s in run.state.slots if s.channel_id]
        rec = decide(
            [Subtask(decision.channel_id, decision.named_failure)],
            world=getattr(run, "world", None),
            occupied_channels=occupied,
        )
        if rec is None:
            run._record("policy_gate", {"result": "someone-else", "channel_id": decision.channel_id})
            return "someone-else"
        run._record("policy_gate", {"result": "legal-but-unwritten", "channel_id": rec.channel_id})
        return "legal-unwritten"
    raise InvariantError("SCHEMA", f"unhandled action {decision.action}")


EVENT_TO_ACTION = {
    "context": "INSPECT",
    "switch_skill": "ACTIVATE_SKILL",
    "set_method": "CHANGE_METHOD",
    "split": "PROPOSE_CHANNEL",
    "set_roster": "PROPOSE_CHANNEL",
    "complete": "STOP",
    "abort": "STOP",
    "review_answer": "HOLD",
}


def replay_log(events: list[dict]) -> list[dict]:
    """Turn a saved run log into (event, action) pairs for imitation."""
    out = []
    for e in events:
        name = e.get("event") or ""
        action = EVENT_TO_ACTION.get(name)
        if not action:
            continue
        if name == "review_answer":
            resp = str((e.get("detail") or {}).get("response") or "")
            if resp == "CHANGE_METHOD":
                action = "CHANGE_METHOD"
            elif resp == "REVISE_GOAL":
                action = "REVISE_GOAL"
            else:
                action = "HOLD"
        out.append({"event": name, "action": action, "detail": e.get("detail") or {}})
    return out


def replay_path(path) -> list[dict]:
    import json
    from pathlib import Path

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return replay_log(raw.get("log") or [])
