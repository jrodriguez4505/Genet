from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .errors import InvariantError
from .models import GATE_ORDER, MAX_WORKERS, SKILLS, GateRecord


@dataclass
class Subtask:
    """A part of the work that could go to its own sub-agent.

    skill is the skill that sub-agent would need (a specialist).
    """

    channel_id: str
    named_failure: str
    covered_by_existing: bool = False
    skill: str = "execute"


@dataclass
class World:
    """What already exists outside the prompt. decide() reads this."""

    existing_files: list[str] = field(default_factory=list)
    existing_channels: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def someone_else_already(subtask: Subtask, world: World | None = None, occupied_channels: list[str] | None = None) -> str | None:
    """Return a reason a second agent is unnecessary. None if the sub-task is still open."""
    if subtask.covered_by_existing:
        return f"{subtask.channel_id} marked covered"
    occupied = set(occupied_channels or [])
    if subtask.channel_id in occupied:
        return f"channel {subtask.channel_id} already staffed"
    world = world or World()
    if subtask.channel_id in world.existing_channels:
        return f"channel {subtask.channel_id} already exists in the world"
    # A file covers a channel when its name (without extension) is the channel.
    # Substring matching let channel "a" be blocked by any path containing an "a".
    for path in world.existing_files:
        if subtask.channel_id and Path(path).stem.lower() == subtask.channel_id.lower():
            return f"file {path} already covers {subtask.channel_id}"
    return None


def decide(
    subtasks: list[Subtask],
    world: World | None = None,
    occupied_channels: list[str] | None = None,
) -> GateRecord | None:
    """
    Three gates in order, judged against the world.
    Someone else already did it → no GateRecord (stay one).
    """
    world = world or World()
    for subtask in subtasks:
        reason = someone_else_already(subtask, world, occupied_channels)
        if reason:
            continue
        if not subtask.named_failure.strip():
            continue
        rec = GateRecord(
            can_someone_else=False,
            should_we=True,
            named_failure=subtask.named_failure,
            could_we=True,
            channel_id=subtask.channel_id,
            order=GATE_ORDER,
        )
        rec.assert_legal()
        return rec
    return None


def refuse_could_we_first() -> None:
    raise InvariantError("INV-9", "could-we is last, not first")


# The refusal for a lone open sub-task. The engine reads it to hand the work to the lead.
LEAD_COVERS = "one open sub-task: the lead covers it without a second agent"

# Channel ids the kernel uses for its own traffic. A sub-agent may not take one.
RESERVED_CHANNELS = {"lead", "lead-plan", "lead-merge", "verify", "merge", "escalate", "report", "peer"}
_CHANNEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass
class Assessment:
    """One proposed sub-task, judged. gates is the three-gate record either way.

    gate names the first gate that refused it ("" when legal). Gates after the
    refusing one were not reached and read False.
    """

    subtask: Subtask
    gates: GateRecord
    refused: str = ""
    gate: str = ""
    # Why "should we" passed: "declared" (the operator required isolation), "measured"
    # (the material does not fit one context) or "stated" (the lead's words alone).
    basis: str = ""

    @property
    def legal(self) -> bool:
        return not self.refused

    def refuse(self, gate: str, reason: str) -> None:
        self.refused, self.gate = reason, gate
        if gate == "can_someone_else":
            self.gates.can_someone_else = True
            self.gates.should_we = self.gates.could_we = False
        elif gate == "should_we":
            self.gates.should_we = self.gates.could_we = False
        else:
            self.gates.could_we = False

    def as_dict(self) -> dict:
        return {
            "channel_id": self.subtask.channel_id,
            "skill": self.subtask.skill,
            "named_failure": self.subtask.named_failure,
            "legal": self.legal,
            "gate": self.gate,
            "refused": self.refused,
            "basis": self.basis,
            "gates": {
                "can_someone_else": self.gates.can_someone_else,
                "should_we": self.gates.should_we,
                "could_we": self.gates.could_we,
                "order": list(self.gates.order),
            },
        }


SPLIT_POLICIES = ("measured", "stated")


def _need(open_: list[Assessment], policy: str, declared: bool, material, context_limit: int | None,
          fit_fraction: float, overhead: int | None = None) -> str:
    """The team's "should we": the basis for a fan-out, or "refuse:<reason>".

    material(subtask) maps the files a sub-task needs to estimated tokens. One agent
    needs every file any sub-task needs, shared files once; a sub-agent needs only
    its own. A measured split needs more than fits in one call, and a split that
    leaves some sub-agent carrying all of it does not help.

    The room in one call is the context limit less overhead, what a call already
    costs before any material (brief and reply). Without a measured overhead it is
    fit_fraction of the limit.
    """
    if declared:
        return "declared"
    if policy == "stated":
        return "stated"
    shares = [material(a.subtask) if material else None for a in open_]
    if context_limit is None or any(s is None for s in shares):
        return "refuse:no measurable reason to split: the material is unknown and isolation was not declared"
    union = {name: tokens for share in shares for name, tokens in share.items()}
    total = sum(union.values())
    if overhead is None:
        room, after = int(context_limit * fit_fraction), ""
    else:
        room, after = max(0, context_limit - overhead), f" after ~{overhead} for the brief and reply"
    if total <= room:
        return f"refuse:fits in one context: ~{total} tokens of material vs {room} available per call{after}"
    if max(sum(share.values()) for share in shares) >= total:
        return f"refuse:a split does not shrink the work: one sub-task alone needs all ~{total} tokens"
    return "measured"


def _could_we(subtask: Subtask) -> str:
    if subtask.skill not in SKILLS:
        return f"no such skill: {subtask.skill}"
    if not _CHANNEL.match(subtask.channel_id or ""):
        return f"channel id not usable: {subtask.channel_id!r}"
    if subtask.channel_id in RESERVED_CHANNELS:
        return f"channel id reserved for the kernel: {subtask.channel_id}"
    return ""


def assess(
    subtasks: list[Subtask],
    *,
    world: World | None = None,
    occupied_channels: list[str] | None = None,
    allow_split: bool = True,
    tier: str = "",
    calls_left: int | None = None,
    worker_slots_left: int = MAX_WORKERS,
    calls_after_split: int = 2,
    worker_cost: Callable[[Subtask], int] | None = None,
    policy: str = "stated",
    declared: bool = False,
    material: Callable[[Subtask], dict[str, int] | None] | None = None,
    context_limit: int | None = None,
    fit_fraction: float = 0.5,
    overhead: int | None = None,
) -> list[Assessment]:
    """
    Judge a proposed task organization, gate by gate, in order. Fails closed.

    Each sub-task:
      1. can someone else  the world covers it, the channel is staffed, it repeats
                           another sub-task, or it is verification (the verifier's job)
      2. should we         it names what goes wrong if a single agent does it
      3. could we          a known skill and a usable channel id
    Then the team:
      1. can someone else  one open sub-task is the lead's job, not a new agent
      2. should we         under policy="measured", a reason a single agent would fail:
                           the operator declared isolation, or the sub-tasks' material
                           (estimated tokens, shared files once) does not fit the room
                           in one call and a split shrinks what each call carries.
                           The room is context_limit less overhead (the measured cost
                           of a call before material), or fit_fraction of context_limit
                           when no overhead is measured.
                           Material that cannot be measured is not a reason.
                           Under policy="stated", the named failures are enough.
      3. could we          the budget tier allows a split; the budget pays for every
                           sub-agent plus merge and verify; the worker cap holds

    A split needs at least two legal sub-tasks. Sub-task order is priority when the
    budget or cap can only pay for some of them. worker_cost is the most calls
    one sub-agent may spend (default 1); calls_after_split covers merge + verify.
    """
    if policy not in SPLIT_POLICIES:
        raise InvariantError("GATES", f"split policy must be one of {SPLIT_POLICIES}, got {policy!r}")
    world = world or World()
    out: list[Assessment] = []
    seen: set[str] = set()
    for subtask in subtasks:
        failure = subtask.named_failure.strip()
        a = Assessment(subtask, GateRecord(False, True, failure or None, True, subtask.channel_id, GATE_ORDER))
        out.append(a)
        covered = someone_else_already(subtask, world, occupied_channels)
        if not covered and subtask.channel_id in seen:
            covered = f"channel {subtask.channel_id} proposed twice"
        if not covered and subtask.skill == "verify":
            covered = "the verifier already covers verification"
        seen.add(subtask.channel_id)
        if covered:
            a.refuse("can_someone_else", covered)
            continue
        if not failure:
            a.refuse("should_we", "no named failure: say what goes wrong if a single agent does it")
            continue
        problem = _could_we(subtask)
        if problem:
            a.refuse("could_we", problem)

    open_ = [a for a in out if a.legal]
    if len(open_) == 1:
        open_[0].refuse("can_someone_else", LEAD_COVERS)
    elif len(open_) >= 2:
        need = _need(open_, policy, declared, material, context_limit, fit_fraction, overhead)
        for a in open_:
            if need.startswith("refuse:"):
                a.refuse("should_we", need[len("refuse:"):])
            else:
                a.basis = need
        open_ = [a for a in open_ if a.legal]
    if len(open_) >= 2 and not allow_split:
        for a in open_:
            a.refuse("could_we", f"budget tier {tier or '?'} does not allow a split")
    elif len(open_) >= 2:
        cost = worker_cost or (lambda _subtask: 1)
        affordable, spend = 0, 0
        for a in open_[: max(0, worker_slots_left)]:
            c = cost(a.subtask)
            if calls_left is not None and spend + c > calls_left - calls_after_split:
                break
            spend += c
            affordable += 1
        if affordable < 2:
            for a in open_:
                a.refuse("could_we", f"budget and worker cap pay for {max(affordable, 0)} sub-agent(s); a split needs two")
        else:
            for a in open_[affordable:]:
                a.refuse("could_we", "budget or worker cap: no room for this sub-agent")
    for a in out:
        if a.legal:
            a.gates.assert_legal()
    return out
