from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .budget import Budget
from .mission import LogEntry, Mission
from .models import Artifact, Cue, Delta, FiveWH, Slot, Status, WhyNote, NoteStatus


def _budget_dict(m: Mission) -> dict | None:
    b = getattr(m, "budget", None)
    if b is None:
        return None
    return {
        "pace": getattr(b, "pace", "run"),
        "max_calls": b.max_calls,
        "max_tokens": b.max_tokens,
        "max_seconds": b.max_seconds,
        "max_tokens_per_call": b.max_tokens_per_call,
        "allow_split": getattr(b, "allow_split", True),
        "allow_adapt": getattr(b, "allow_adapt", True),
    }


def mission_to_dict(m: Mission) -> dict:
    return {
        "id": m.id,
        "status": m.status.value,
        "picture": {
            "who_head_id": m.picture.who_head_id,
            "slots": [asdict(s) for s in m.picture.slots],
            "primary": m.picture.primary,
            "effect": m.picture.effect,
            "success_criteria": m.picture.success_criteria,
            "tempo": m.picture.tempo,
            "decision_points": m.picture.decision_points,
            "current_picture": m.picture.current_picture,
            "step_off_picture": m.picture.step_off_picture,
            "end_state": m.picture.end_state,
            "purpose": m.picture.purpose,
            "method": m.picture.method,
            "projections": m.picture.projections,
            "context_sufficient": m.picture.context_sufficient,
            "axes": m.picture.axes,
            "abort_criteria": m.picture.abort_criteria,
        },
        "notes": {
            k: {
                "id": n.id,
                "body": n.body,
                "status": n.status.value,
                "response": n.response,
                "reason": n.reason,
                "kind": getattr(n, "kind", "why"),
            }
            for k, n in m.notes.items()
        },
        "cues": {k: asdict(c) for k, c in m.cues.items()},
        "artifacts": [asdict(a) for a in m.artifacts],
        "deltas": [asdict(d) for d in m.deltas],
        "open_nets": list(m.open_nets),
        "log": [{"event": e.event, "detail": e.detail, "ts": getattr(e, "ts", 0)} for e in m.log],
        "failed_stop_rules": m.failed_stop_rules,
        "last_verify": getattr(m, "last_verify", None),
        "who_open": list(getattr(m, "who_open", []) or []),
        "adapter_name": getattr(m, "adapter_name", ""),
        "calls": [
            {k: v for k, v in c.items() if k != "packet"}
            for c in getattr(m, "calls", [])
        ],
        "stop_reason": getattr(m, "stop_reason", ""),
        "budget": _budget_dict(m),
        "summary": m.summary(),
    }


def save_mission(m: Mission, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mission_to_dict(m), indent=2), encoding="utf-8")
    return path


def load_mission(path: Path) -> Mission:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    pic = raw["picture"]
    picture = FiveWH(
        who_head_id=pic["who_head_id"],
        slots=[Slot(**s) for s in pic["slots"]],
        primary=pic["primary"],
        effect=pic["effect"],
        success_criteria=pic["success_criteria"],
        tempo=pic["tempo"],
        decision_points=pic["decision_points"],
        current_picture=pic["current_picture"],
        step_off_picture=pic.get("step_off_picture", ""),
        end_state=pic["end_state"],
        purpose=pic["purpose"],
        method=pic["method"],
        projections=pic.get("projections", []),
        context_sufficient=pic.get("context_sufficient", False),
        axes=pic.get("axes", []),
        abort_criteria=pic.get("abort_criteria", []),
    )
    m = Mission(id=raw["id"], picture=picture)
    m.log.clear()
    m.status = Status(raw["status"])
    m.failed_stop_rules = list(raw.get("failed_stop_rules", []))
    m.notes = {
        k: WhyNote(
            id=n["id"],
            body=n["body"],
            status=NoteStatus(n["status"]),
            response=n.get("response"),
            reason=n.get("reason"),
            kind=n.get("kind", "why"),
        )
        for k, n in raw.get("notes", {}).items()
    }
    m.cues = {k: Cue(**c) for k, c in raw.get("cues", {}).items()}
    m.artifacts = [Artifact(**a) for a in raw.get("artifacts", [])]
    m.deltas = [Delta(**d) for d in raw.get("deltas", [])]
    m.open_nets = list(raw.get("open_nets") or ["element", "up"])
    m.log = [LogEntry(event=e["event"], detail=e["detail"], ts=e.get("ts") or 0) for e in raw.get("log", [])]
    m.calls = list(raw.get("calls") or [])
    m.last_verify = raw.get("last_verify")
    m.who_open = list(raw.get("who_open") or [])
    m.adapter_name = raw.get("adapter_name") or ""
    m.stop_reason = raw.get("stop_reason") or ""
    raw_b = raw.get("budget")
    if raw_b:
        m.budget = Budget(
            max_calls=raw_b.get("max_calls", 12),
            max_tokens=raw_b.get("max_tokens", 50_000),
            max_seconds=raw_b.get("max_seconds", 120),
            max_tokens_per_call=raw_b.get("max_tokens_per_call", 4_000),
            allow_split=raw_b.get("allow_split", True),
            allow_adapt=raw_b.get("allow_adapt", True),
            pace=raw_b.get("pace", "run"),
        )
    return m
