from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


FUNCTIONS = ("lead", "worker", "verifier", "memory", "reviewer")
SKILLS = ("execute", "retrieve", "reason", "draft", "simulate", "observe", "verify")
# Tool allowlist per skill. Runnable tools (see tools.py): read, retrieve, observe.
# write / simulate / verify act on nothing outside; the result goes in the artifact.
SKILL_TOOLS = {
    "execute": ("write",),
    "retrieve": ("retrieve", "read"),
    "reason": ("write",),
    "draft": ("write",),
    "simulate": ("simulate",),
    "observe": ("observe", "read"),
    "verify": ("verify",),
}
AXES = ("parallel", "fallback", "reroute", "sequential", "reverse", "fan_in")
GATE_ORDER = ("can_someone_else", "should_we", "could_we")
LEAD_RESPONSES = ("KEEP_ROSTER", "CHANGE_METHOD", "REVISE_GOAL", "DEFER")
MAX_WORKERS = 4
# Message streams: merge (sub-agent results into shared context), escalate (to the lead),
# report (to the operator), peer (to another run; never merged).
STREAMS = ("merge", "escalate", "report", "peer")


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
        if self.skill not in SKILLS:
            raise ValueError(f"unknown skill: {self.skill}")
        if not self.tools:
            self.tools = list(SKILL_TOOLS.get(self.skill, ("write",)))


@dataclass
class Artifact:
    claim: str
    evidence: list[str]
    uncertainty: str
    channel_id: str
    context_update: str
    requests: list[str] = field(default_factory=list)

    def validate(self) -> None:
        from .errors import InvariantError

        if not self.claim.strip():
            raise InvariantError("SCHEMA", "artifact.claim is empty")
        if not self.channel_id.strip():
            raise InvariantError("SCHEMA", "artifact.channel_id is empty")


@dataclass
class ReviewNote:
    id: str
    body: str
    status: NoteStatus = NoteStatus.OPEN
    response: Optional[str] = None
    reason: Optional[str] = None
    kind: str = "review"


@dataclass
class Delta:
    """A typed update to the shared context, carried on one stream."""

    claim: str
    evidence: list[str]
    uncertainty: str
    channel_id: str
    stream: str = "merge"

    def __post_init__(self):
        if self.stream not in STREAMS:
            raise ValueError(f"unknown stream: {self.stream}")


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
        # Checked in gate order: the first gate that fails names the refusal.
        if self.can_someone_else:
            raise InvariantError(
                "GATE-1",
                "can someone else is true — assign or refuse, do not spawn",
            )
        if not self.should_we or not self.named_failure:
            raise InvariantError("INV-8", "split requires a named failure (should we)")
        if not self.could_we or not self.channel_id:
            raise InvariantError("GATE-3", "could we failed — no independent channel")


@dataclass
class RunState:
    lead_id: str
    slots: list[Slot]
    primary: str
    goal: str
    success_criteria: list[str]
    cadence: str
    checkpoints: list[str]
    context: str
    done_when: str
    purpose: str
    method: str
    initial_context: str = ""
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
        from .errors import InvariantError

        raise InvariantError("ROSTER", f"no slot {slot_id!r} on the roster")
