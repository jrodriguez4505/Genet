"""Runtime checks bound to schemas/artifact.json and schemas/run_state.json."""

from __future__ import annotations

import json
from pathlib import Path

from .errors import InvariantError
from .models import Artifact, RunState

_ROOT = Path(__file__).resolve().parent.parent
_ARTIFACT = _ROOT / "schemas" / "artifact.json"
_STATE = _ROOT / "schemas" / "run_state.json"


def _required(path: Path, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if not path.exists():
        return fallback
    spec = json.loads(path.read_text())
    return tuple(spec.get("required") or fallback)


REQUIRED_ARTIFACT = _required(_ARTIFACT, ("claim", "evidence", "uncertainty", "channel_id", "context_update"))
REQUIRED_STATE = _required(_STATE, ("roster", "goal", "schedule", "context", "purpose", "method"))


def validate_artifact(artifact: Artifact) -> None:
    artifact.validate()
    for key in REQUIRED_ARTIFACT:
        if not hasattr(artifact, key):
            raise InvariantError("SCHEMA", f"artifact missing {key}")
    if not artifact.claim.strip():
        raise InvariantError("SCHEMA", "artifact.claim is empty")
    if not artifact.channel_id.strip():
        raise InvariantError("SCHEMA", "artifact.channel_id required")
    if artifact.evidence is None:
        raise InvariantError("SCHEMA", "artifact.evidence required")


def state_contract(pic: RunState) -> dict:
    return {
        "roster": {"lead_id": pic.lead_id, "slots": [s.id for s in pic.slots], "primary": pic.primary},
        "goal": {"goal": pic.goal, "success_criteria": list(pic.success_criteria)},
        "schedule": {"cadence": pic.cadence, "checkpoints": list(pic.checkpoints)},
        "context": {"context": pic.context, "done_when": pic.done_when},
        "purpose": {"purpose": pic.purpose},
        "method": {"method": pic.method, "axes": list(pic.axes)},
    }


def validate_state(pic: RunState) -> None:
    data = state_contract(pic)
    for key in REQUIRED_STATE:
        if key not in data:
            raise InvariantError("SCHEMA", f"run state missing {key}")
    if not str(pic.goal).strip():
        raise InvariantError("SCHEMA", "cannot complete: the goal is empty")
    if not str(pic.purpose).strip():
        raise InvariantError("SCHEMA", "cannot complete: the purpose is empty")
    if not str(pic.context).strip():
        raise InvariantError("SCHEMA", "cannot complete: the context is empty")
    if not str(pic.method).strip():
        raise InvariantError("SCHEMA", "cannot complete: the method is empty")
    if not pic.success_criteria:
        raise InvariantError("SCHEMA", "cannot complete: no success criteria")
