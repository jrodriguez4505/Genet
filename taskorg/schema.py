"""Runtime checks bound to schemas/artifact.json and schemas/five_wh.json."""

from __future__ import annotations

import json
from pathlib import Path

from .errors import InvariantError
from .models import Artifact, FiveWH

_ROOT = Path(__file__).resolve().parent.parent
_ARTIFACT = _ROOT / "schemas" / "artifact.json"
_FIVE = _ROOT / "schemas" / "five_wh.json"


def _required(path: Path, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if not path.exists():
        return fallback
    spec = json.loads(path.read_text())
    return tuple(spec.get("required") or fallback)


REQUIRED_ARTIFACT = _required(_ARTIFACT, ("claim", "evidence", "uncertainty", "channel_id", "delta_to_picture"))
REQUIRED_FIVE = _required(_FIVE, ("who", "what", "when", "where", "why", "how"))


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


def picture_contract(pic: FiveWH) -> dict:
    return {
        "who": {"head_id": pic.who_head_id, "slots": [s.id for s in pic.slots], "primary": pic.primary},
        "what": {"effect": pic.effect, "success_criteria": list(pic.success_criteria)},
        "when": {"tempo": pic.tempo, "decision_points": list(pic.decision_points)},
        "where": {"current_picture": pic.current_picture, "end_state": pic.end_state},
        "why": {"purpose": pic.purpose},
        "how": {"method": pic.method, "axes": list(pic.axes)},
    }


def validate_five_wh(pic: FiveWH) -> None:
    data = picture_contract(pic)
    for key in REQUIRED_FIVE:
        if key not in data:
            raise InvariantError("SCHEMA", f"context object missing {key}")
    if not str(pic.effect).strip():
        raise InvariantError("SCHEMA", "COMPLETE missing What")
    if not str(pic.purpose).strip():
        raise InvariantError("SCHEMA", "COMPLETE missing Why")
    if not str(pic.current_picture).strip():
        raise InvariantError("SCHEMA", "COMPLETE missing Where")
    if not str(pic.method).strip():
        raise InvariantError("SCHEMA", "COMPLETE missing How")
    if not pic.success_criteria:
        raise InvariantError("SCHEMA", "COMPLETE missing success criteria")
