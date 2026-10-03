from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .budget import Budget
from .models import SKILLS, Artifact, Cue, Delta, NoteStatus, ReviewNote, RunState, Slot, Status
from .run import LogEntry, Run


def _budget_dict(m: Run) -> dict | None:
    b = getattr(m, "budget", None)
    if b is None:
        return None
    return {
        "tier": getattr(b, "tier", "open"),
        "max_calls": b.max_calls,
        "max_tokens": b.max_tokens,
        "max_seconds": b.max_seconds,
        "max_tokens_per_call": b.max_tokens_per_call,
        "allow_split": getattr(b, "allow_split", True),
        "allow_adapt": getattr(b, "allow_adapt", True),
    }


def run_to_dict(m: Run) -> dict:
    return {
        "format": 2,
        "id": m.id,
        "status": m.status.value,
        "state": {
            "lead_id": m.state.lead_id,
            "slots": [asdict(s) for s in m.state.slots],
            "primary": m.state.primary,
            "goal": m.state.goal,
            "success_criteria": m.state.success_criteria,
            "cadence": m.state.cadence,
            "checkpoints": m.state.checkpoints,
            "context": m.state.context,
            "initial_context": m.state.initial_context,
            "done_when": m.state.done_when,
            "purpose": m.state.purpose,
            "method": m.state.method,
            "projections": m.state.projections,
            "context_sufficient": m.state.context_sufficient,
            "axes": m.state.axes,
            "abort_criteria": m.state.abort_criteria,
        },
        "notes": {
            k: {
                "id": n.id,
                "body": n.body,
                "status": n.status.value,
                "response": n.response,
                "reason": n.reason,
                "kind": n.kind,
            }
            for k, n in m.notes.items()
        },
        "cues": {k: asdict(c) for k, c in m.cues.items()},
        "artifacts": [asdict(a) for a in m.artifacts],
        "deltas": [asdict(d) for d in m.deltas],
        "open_streams": list(m.open_streams),
        "log": [{"event": e.event, "detail": e.detail, "ts": getattr(e, "ts", 0)} for e in m.log],
        "failed_stop_rules": m.failed_stop_rules,
        "last_verify": getattr(m, "last_verify", None),
        "roster_at_start": list(getattr(m, "roster_at_start", []) or []),
        "adapter_name": getattr(m, "adapter_name", ""),
        "calls": [
            {k: v for k, v in c.items() if k != "packet"}
            for c in getattr(m, "calls", [])
        ],
        "stop_reason": getattr(m, "stop_reason", ""),
        "budget": _budget_dict(m),
        "summary": m.summary(),
    }


def save_run(m: Run, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run_to_dict(m), indent=2), encoding="utf-8")
    return path


# Files saved before the 0.2 rename used older field names. Read them, write the new ones.
_LEGACY_STATE = {
    "who_head_id": "lead_id", "effect": "goal", "tempo": "cadence", "decision_points": "checkpoints",
    "current_picture": "context", "step_off_picture": "initial_context", "end_state": "done_when",
    "main_effort": "primary", "can_see_other_side": "context_sufficient",
}
_LEGACY_FUNCTION = {"head": "lead", "why": "reviewer"}
_LEGACY_KIND = {"why": "review", "plan_wrong": "replan"}
_LEGACY_STREAM = {"element": "merge", "up": "escalate", "out": "report", "adjacent": "peer"}
_LEGACY_TIER = {"crawl": "tight", "walk": "normal", "run": "open"}


def _legacy_skill(slot: dict) -> str:
    """The oldest files name skills differently; anything unknown becomes execute."""
    skill = slot.get("skill") or slot.get("hot_qual") or "execute"
    return skill if skill in SKILLS else "execute"


def _upgrade(raw: dict) -> dict:
    if "state" in raw:
        return raw
    raw = dict(raw)
    state = {}
    for k, v in raw.pop("picture").items():
        state.setdefault(_LEGACY_STATE.get(k, k), v)
    state["slots"] = [
        {
            "id": s["id"],
            "function": _LEGACY_FUNCTION.get(s["function"], s["function"]),
            "skill": _legacy_skill(s),
            "channel_id": s.get("channel_id"),
            "tools": s.get("tools") or [],
        }
        for s in state["slots"]
    ]
    raw["state"] = state
    raw["notes"] = {k: n | {"kind": _LEGACY_KIND.get(n.get("kind", "why"), n.get("kind"))} for k, n in raw.get("notes", {}).items()}
    raw["artifacts"] = [
        {("context_update" if k == "delta_to_picture" else k): v for k, v in a.items()} for a in raw.get("artifacts", [])
    ]
    raw["deltas"] = [
        {k: v for k, v in d.items() if k != "net"} | {"stream": _LEGACY_STREAM.get(d.get("net", "element"), "merge")}
        for d in raw.get("deltas", [])
    ]
    raw["open_streams"] = [_LEGACY_STREAM.get(n, n) for n in raw.pop("open_nets", ["element", "up"])]
    raw["roster_at_start"] = raw.pop("who_open", [])
    if raw.get("budget"):
        b = dict(raw["budget"])
        b["tier"] = _LEGACY_TIER.get(b.pop("pace", "run"), "open")
        raw["budget"] = b
    return raw


def load_run(path: Path) -> Run:
    raw = _upgrade(json.loads(Path(path).read_text(encoding="utf-8")))
    st = raw["state"]
    state = RunState(
        lead_id=st["lead_id"],
        slots=[Slot(**s) for s in st["slots"]],
        primary=st["primary"],
        goal=st["goal"],
        success_criteria=st["success_criteria"],
        cadence=st["cadence"],
        checkpoints=st["checkpoints"],
        context=st["context"],
        initial_context=st.get("initial_context", ""),
        done_when=st["done_when"],
        purpose=st["purpose"],
        method=st["method"],
        projections=st.get("projections", []),
        context_sufficient=st.get("context_sufficient", False),
        axes=st.get("axes", []),
        abort_criteria=st.get("abort_criteria", []),
    )
    m = Run(id=raw["id"], state=state)
    m.log.clear()
    m.status = Status(raw["status"])
    m.failed_stop_rules = list(raw.get("failed_stop_rules", []))
    m.notes = {
        k: ReviewNote(
            id=n["id"],
            body=n["body"],
            status=NoteStatus(n["status"]),
            response=n.get("response"),
            reason=n.get("reason"),
            kind=n.get("kind", "review"),
        )
        for k, n in raw.get("notes", {}).items()
    }
    m.cues = {k: Cue(**c) for k, c in raw.get("cues", {}).items()}
    m.artifacts = [Artifact(**a) for a in raw.get("artifacts", [])]
    m.deltas = [Delta(**d) for d in raw.get("deltas", [])]
    m.open_streams = list(raw.get("open_streams") or ["merge", "escalate"])
    m.log = [LogEntry(event=e["event"], detail=e["detail"], ts=e.get("ts") or 0) for e in raw.get("log", [])]
    m.calls = list(raw.get("calls") or [])
    m.last_verify = raw.get("last_verify")
    m.roster_at_start = list(raw.get("roster_at_start") or [])
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
            tier=raw_b.get("tier", "open"),
        )
    return m
