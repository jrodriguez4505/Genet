from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .errors import InvariantError
from .models import GATE_ORDER, MAX_WORKERS, QUALS, GateRecord


@dataclass
class Seam:
    """A part of the work that could go to its own element.

    skill is the qualification the element would need (a specialist).
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


def someone_else_already(seam: Seam, world: World | None = None, occupied_channels: list[str] | None = None) -> str | None:
    """Return a reason if a second body is unnecessary. None if the seam is still open."""
    if seam.covered_by_existing:
        return f"{seam.channel_id} marked covered"
    occupied = set(occupied_channels or [])
    if seam.channel_id in occupied:
        return f"channel {seam.channel_id} already staffed"
    world = world or World()
    if seam.channel_id in world.existing_channels:
        return f"channel {seam.channel_id} already exists in the world"
    # A file covers a channel when its name (without extension) is the channel.
    # Substring matching let channel "a" be blocked by any path containing an "a".
    for path in world.existing_files:
        if seam.channel_id and Path(path).stem.lower() == seam.channel_id.lower():
            return f"file {path} already covers {seam.channel_id}"
    return None


def decide(
    seams: list[Seam],
    world: World | None = None,
    occupied_channels: list[str] | None = None,
) -> GateRecord | None:
    """
    Three gates in order, judged against the world.
    Someone else already did it → no GateRecord (stay one).
    """
    world = world or World()
    for seam in seams:
        reason = someone_else_already(seam, world, occupied_channels)
        if reason:
            continue
        if not seam.named_failure.strip():
            continue
        rec = GateRecord(
            can_someone_else=False,
            should_we=True,
            named_failure=seam.named_failure,
            could_we=True,
            channel_id=seam.channel_id,
            order=GATE_ORDER,
        )
        rec.assert_legal()
        return rec
    return None


def refuse_could_we_first() -> None:
    raise InvariantError("INV-9", "could-we is last, not first")


# Channel ids the kernel uses for its own traffic. An element may not take one.
RESERVED_CHANNELS = {"head", "head-plan", "head-integrate", "verify", "element", "up", "out", "adjacent"}
_CHANNEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass
class Assessment:
    """One proposed element, judged. gates is the three-gate record either way.

    gate names the first gate that refused it ("" when legal). Gates after the
    refusing one were not reached and read False.
    """

    seam: Seam
    gates: GateRecord
    refused: str = ""
    gate: str = ""

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
            "channel_id": self.seam.channel_id,
            "skill": self.seam.skill,
            "named_failure": self.seam.named_failure,
            "legal": self.legal,
            "gate": self.gate,
            "refused": self.refused,
            "gates": {
                "can_someone_else": self.gates.can_someone_else,
                "should_we": self.gates.should_we,
                "could_we": self.gates.could_we,
                "order": list(self.gates.order),
            },
        }


def _could_we(seam: Seam) -> str:
    if seam.skill not in QUALS:
        return f"no such specialty: {seam.skill}"
    if not _CHANNEL.match(seam.channel_id or ""):
        return f"channel id not usable: {seam.channel_id!r}"
    if seam.channel_id in RESERVED_CHANNELS:
        return f"channel id reserved for the kernel: {seam.channel_id}"
    return ""


def assess(
    seams: list[Seam],
    *,
    world: World | None = None,
    occupied_channels: list[str] | None = None,
    allow_split: bool = True,
    pace: str = "",
    calls_left: int | None = None,
    worker_slots_left: int = MAX_WORKERS,
    calls_after_split: int = 2,
    element_cost: Callable[[Seam], int] | None = None,
) -> list[Assessment]:
    """
    Judge a proposed task organization, gate by gate, in order. Fails closed.

    Each seam:
      1. can someone else  the world covers it, the channel is staffed, it repeats
                           another seam, or it is verification (the verifier's job)
      2. should we         it names what goes wrong if one body does it
      3. could we          a known specialty and a usable channel id
    Then the team:
      1. can someone else  one open seam is the lead's job, not a new body
      3. could we          the pace allows a split; the budget pays for every element
                           plus integrate and verify; the worker cap holds

    A split needs at least two legal elements. Seam order is priority when the
    budget or cap can only pay for some of them. element_cost is the most calls
    one element may spend (default 1); calls_after_split covers integrate + verify.
    """
    world = world or World()
    out: list[Assessment] = []
    seen: set[str] = set()
    for seam in seams:
        failure = seam.named_failure.strip()
        a = Assessment(seam, GateRecord(False, True, failure or None, True, seam.channel_id, GATE_ORDER))
        out.append(a)
        covered = someone_else_already(seam, world, occupied_channels)
        if not covered and seam.channel_id in seen:
            covered = f"channel {seam.channel_id} proposed twice"
        if not covered and seam.skill == "verify":
            covered = "the verifier already covers verification"
        seen.add(seam.channel_id)
        if covered:
            a.refuse("can_someone_else", covered)
            continue
        if not failure:
            a.refuse("should_we", "no named failure: say what goes wrong if one body does it")
            continue
        problem = _could_we(seam)
        if problem:
            a.refuse("could_we", problem)

    open_ = [a for a in out if a.legal]
    if len(open_) == 1:
        open_[0].refuse("can_someone_else", "one open seam: the lead covers it without a second body")
    elif len(open_) >= 2 and not allow_split:
        for a in open_:
            a.refuse("could_we", f"pace {pace or '?'} does not allow a split")
    elif len(open_) >= 2:
        cost = element_cost or (lambda _seam: 1)
        affordable, spend = 0, 0
        for a in open_[: max(0, worker_slots_left)]:
            c = cost(a.seam)
            if calls_left is not None and spend + c > calls_left - calls_after_split:
                break
            spend += c
            affordable += 1
        if affordable < 2:
            for a in open_:
                a.refuse("could_we", f"budget and worker cap pay for {max(affordable, 0)} element(s); a split needs two")
        else:
            for a in open_[affordable:]:
                a.refuse("could_we", "budget or worker cap: no room for this element")
    for a in out:
        if a.legal:
            a.gates.assert_legal()
    return out
