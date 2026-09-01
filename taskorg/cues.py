from __future__ import annotations

from .mission import Mission
from .models import Cue


def fire_auto_cues(mission: Mission) -> list[Cue]:
    minted: list[Cue] = []
    claims = [a.claim for a in mission.artifacts]
    channels = [a.channel_id for a in mission.artifacts if a.channel_id not in ("verify", "head-integrate")]

    if len(channels) >= 2 and len(set(channels)) >= 2:
        cue = Cue(
            id=f"conflict-{mission.id}",
            trigger="two Workers on distinct channels",
            payload="integrate; open Why if pictures contradict",
            target=mission.picture.who_head_id,
            expiry="mission-end",
        )
        if cue.id not in mission.cues:
            mission.mint_cue(cue)
            minted.append(cue)

    if mission.picture.context_sufficient and mission.picture.worker_count() == 0:
        cue = Cue(
            id=f"look-enough-{mission.id}",
            trigger="look completed with no split",
            payload="could this have been one: default yes",
            target=mission.picture.who_head_id,
            expiry="mission-end",
        )
        if cue.id not in mission.cues:
            mission.mint_cue(cue)
            minted.append(cue)

    if any("PASS" not in c.upper() and "FAIL" in c.upper() for c in claims):
        cue = Cue(
            id=f"rework-{mission.id}",
            trigger="verifier did not pass",
            payload="method exhausted path",
            target=mission.picture.who_head_id,
            expiry="mission-end",
        )
        if cue.id not in mission.cues:
            mission.mint_cue(cue)
            minted.append(cue)
    return minted


def admit_cues(mission: Mission) -> list[str]:
    """Turn unadmitted cues into Why notes. Head still has to answer."""
    opened = []
    for cue in mission.cues.values():
        note_id = f"why-{cue.id}"
        if note_id in mission.notes:
            continue
        mission.submit_why(f"{cue.trigger}: {cue.payload}", note_id)
        opened.append(note_id)
    return opened
