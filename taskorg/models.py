from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


FUNCTIONS = ("head", "worker", "verifier", "memory", "why")
QUALS = ("execute", "retrieve", "reason", "draft", "simulate", "observe", "verify")
QUAL_TOOLS = {
    "execute": ("write",),
    "retrieve": ("retrieve",),
    "reason": ("write",),
    "draft": ("write",),
    "simulate": ("simulate",),
    "observe": ("observe", "read"),
    "verify": ("verify",),
}
AXES = ("parallel", "fallback", "reroute", "sequential", "reverse", "fan_in")
GATE_ORDER = ("can_someone_else", "should_we", "could_we")
HEAD_RESPONSES = ("KEEP_ROSTER", "CHANGE_METHOD", "REVISE_GOAL", "DEFER")
MAX_WORKERS = 4
NETS = ("element", "up", "out", "adjacent")


class Status(str, Enum):
    ACTIVE = "active"
    HOLD = "hold"
    COMPLETE = "complete"
    ABORT = "abort"


class NoteStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    DEFERRED = "deferred"


@dataclass
class Slot:
    id: str
    function: str
    skill: str = "execute"
    channel_id: Optional[str] = None
    tools: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.function not in FUNCTIONS:
            raise ValueError(f"unknown function: {self.function}")
        if self.skill not in QUALS:
            raise ValueError(f"unknown skill: {self.skill}")
        if not self.tools:
            self.tools = list(QUAL_TOOLS.get(self.skill, ("write",)))


@dataclass
class Artifact:
    claim: str
    evidence: list[str]
    uncertainty: str
    channel_id: str
    delta_to_picture: str
    requests: list[str] = field(default_factory=list)

    def validate(self) -> None:
        from .errors import InvariantError

        if not self.claim.strip():
            raise InvariantError("SCHEMA", "artifact.claim is empty")
        if not self.channel_id.strip():
            raise InvariantError("SCHEMA", "artifact.channel_id is empty")


@dataclass
class WhyNote:
    id: str
    body: str
    status: NoteStatus = NoteStatus.OPEN
    response: Optional[str] = None
    reason: Optional[str] = None
    kind: str = "why"


@dataclass
class Delta:
    """Typed mark on shared context. Element-net payload."""

    claim: str
    evidence: list[str]
    uncertainty: str
    channel_id: str
    net: str = "element"

    def __post_init__(self):
        if self.net not in NETS:
            raise ValueError(f"unknown net: {self.net}")


@dataclass
class Cue:
    id: str
    trigger: str
    payload: str
    target: str
    expiry: str
    priority: int = 0


@dataclass
class GateRecord:
    can_someone_else: bool
    should_we: bool
    named_failure: Optional[str]
    could_we: bool
    channel_id: Optional[str]
    order: tuple[str, str, str] = GATE_ORDER

    def assert_legal(self) -> None:
        from .errors import InvariantError

        if self.order != GATE_ORDER:
            raise InvariantError(
                "INV-9",
                "gates must be recorded in order: can_someone_else, should_we, could_we",
            )
        if not self.should_we or not self.named_failure:
            raise InvariantError("INV-8", "split requires a named failure (should we)")
        if self.can_someone_else:
            raise InvariantError(
                "GATE-1",
                "can someone else is true — assign or refuse, do not spawn",
            )
        if not self.could_we or not self.channel_id:
            raise InvariantError("GATE-3", "could we failed — no independent channel")


@dataclass
class FiveWH:
    who_head_id: str
    slots: list[Slot]
    primary: str
    effect: str
    success_criteria: list[str]
    tempo: str
    decision_points: list[str]
    current_picture: str
    end_state: str
    purpose: str
    method: str
    step_off_picture: str = ""
    projections: list[str] = field(default_factory=list)
    context_sufficient: bool = False
    axes: list[str] = field(default_factory=list)
    abort_criteria: list[str] = field(default_factory=list)

    def worker_count(self) -> int:
        return sum(1 for s in self.slots if s.function == "worker")

    def slot(self, slot_id: str) -> Slot:
        for s in self.slots:
            if s.id == slot_id:
                return s
        raise KeyError(slot_id)
