from __future__ import annotations

from .run import Run
from .models import Cue


def fire_auto_cues(run: Run) -> list[Cue]:
    minted: list[Cue] = []
    claims = [a.claim for a in run.artifacts]
    channels = [a.channel_id for a in run.artifacts if a.channel_id not in ("verify", "lead-merge", "lead-plan")]

    if len(channels) >= 2 and len(set(channels)) >= 2:
        cue = Cue(
            id=f"conflict-{run.id}",
            trigger="two Workers on distinct channels",
            payload="merge; open a review if the results contradict",
            target=run.state.lead_id,
            expiry="run-end",
        )
        if cue.id not in run.cues:
            run.mint_cue(cue)
            minted.append(cue)

    if run.state.context_sufficient and run.state.worker_count() == 0:
        cue = Cue(
            id=f"context-enough-{run.id}",
            trigger="context checked with no fan-out",
            payload="could a single agent have done this: default yes",
            target=run.state.lead_id,
            expiry="run-end",
        )
        if cue.id not in run.cues:
            run.mint_cue(cue)
            minted.append(cue)

    if any("PASS" not in c.upper() and "FAIL" in c.upper() for c in claims):
        cue = Cue(
            id=f"rework-{run.id}",
            trigger="verifier did not pass",
            payload="method exhausted path",
            target=run.state.lead_id,
            expiry="run-end",
        )
        if cue.id not in run.cues:
            run.mint_cue(cue)
            minted.append(cue)
    return minted


def admit_cues(run: Run) -> list[str]:
    """Turn unadmitted triggers into reviews. The lead still has to answer."""
    opened = []
    for cue in run.cues.values():
        note_id = f"review-{cue.id}"
        if note_id in run.notes:
            continue
        run.open_review(f"{cue.trigger}: {cue.payload}", note_id)
        opened.append(note_id)
    return opened
