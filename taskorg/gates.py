from __future__ import annotations

from dataclasses import dataclass, field

from .errors import InvariantError
from .models import GATE_ORDER, GateRecord


@dataclass
class Seam:
    channel_id: str
    named_failure: str
    covered_by_existing: bool = False


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
    for path in world.existing_files:
        if seam.channel_id and seam.channel_id in path:
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
