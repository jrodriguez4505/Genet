from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from .budget import Budget
from .errors import InvariantError
from .gates import World
from .models import SKILL_TOOLS, SKILLS, Artifact, Cue, Delta, NoteStatus, ReviewNote, RunState, Slot, Status
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
        # Time already spent, so a loaded run does not get a fresh clock.
        "elapsed": round(b.elapsed(), 3),
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
        # What already exists outside the run; the gates read it, so it travels with the run.
        "world": asdict(m.world) if getattr(m, "world", None) else None,
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
_LEGACY_EVENT = {
    "mission_open": "run_open", "look": "context", "slide": "switch_skill", "set_how": "set_method",
    "why_submit": "review_open", "why_respond": "review_answer", "write_who": "set_roster",
    "write_net": "open_stream", "adjacent_in": "peer_in", "human_override_who": "human_override_roster",
}
_LEGACY_DETAIL = {"net": "stream", "who": "roster", "picture": "context"}


def _legacy_entry(e: dict) -> dict:
    """One log entry in today's vocabulary: event names, detail keys, and stream and review names."""
    detail = {}
    for k, v in (e.get("detail") or {}).items():
        key = _LEGACY_DETAIL.get(k, k)
        if k == "net":
            v = _LEGACY_STREAM.get(v, v)
        elif k == "kind":
            v = _LEGACY_KIND.get(v, v)
        detail[key] = v
    return {**e, "event": _LEGACY_EVENT.get(e.get("event"), e.get("event")), "detail": detail}


def _legacy_skill(slot: dict) -> str:
    """The oldest files name skills differently; anything unknown becomes execute."""
    skill = slot.get("skill") or slot.get("hot_qual") or "execute"
    return skill if skill in SKILLS else "execute"


def _upgrade(raw: dict) -> dict:
    if "state" in raw:
        # Format 2, possibly re-saved from an older file by older code: the log may still use old names.
        log = raw.get("log")
        return raw | {"log": [_legacy_entry(e) for e in log if isinstance(e, dict)]} if isinstance(log, list) else raw
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
    raw["log"] = [_legacy_entry(e) for e in raw.get("log", []) if isinstance(e, dict)]
    raw["roster_at_start"] = raw.pop("who_open", [])
    if raw.get("budget"):
        b = dict(raw["budget"])
        b["tier"] = _LEGACY_TIER.get(b.pop("pace", "run"), "open")
        raw["budget"] = b
    return raw


def _slot(saved: dict) -> Slot:
    """A saved slot. Its tools are never wider than its skill allows, whatever the file says."""
    saved = dict(saved)
    allowed = SKILL_TOOLS.get(saved.get("skill") or "execute", ())
    saved["tools"] = [t for t in saved.get("tools") or [] if t in allowed]
    return Slot(**saved)


def load_run(path: Path) -> Run:
    """A saved run. The file is untrusted input: anything malformed is refused as a PERSIST error."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise InvariantError("PERSIST", f"cannot read run file: {path}: {e.strerror or type(e).__name__}") from e
    try:
        raw = json.loads(text)
        if not isinstance(raw, dict):
            raise TypeError("a run file is a JSON object")
        raw = _upgrade(raw)
        _check_types(raw)
        return _from_dict(raw)
    except InvariantError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as e:
        raise InvariantError("PERSIST", f"not a valid run file: {path}: {type(e).__name__}: {str(e)[:120]}") from e


def _need(cond: bool, what: str) -> None:
    if not cond:
        raise TypeError(what)


def _strs(v, what: str) -> None:
    _need(isinstance(v, list) and all(isinstance(x, str) for x in v), f"{what}: a list of strings")


def _number(v, what: str, *, optional: bool = False) -> None:
    if optional and v is None:
        return
    _need(isinstance(v, (int, float)) and not isinstance(v, bool), f"{what}: a number")


def _check_types(raw: dict) -> None:
    """Field types, so a hand-edited or hostile file fails here, not later inside a read command."""
    _need(isinstance(raw.get("id"), str) and isinstance(raw.get("status"), str), "id and status: strings")
    st = raw.get("state")
    _need(isinstance(st, dict), "state: an object")
    _need(isinstance(st.get("slots"), list) and all(isinstance(s, dict) for s in st["slots"]), "state.slots: objects")
    for k in ("lead_id", "primary", "goal", "cadence", "context", "done_when", "purpose", "method"):
        _need(isinstance(st.get(k), str), f"state.{k}: a string")
    for k in ("success_criteria", "checkpoints", "projections", "axes", "abort_criteria"):
        if k in st:
            _strs(st[k], f"state.{k}")
    for k in ("open_streams", "roster_at_start", "failed_stop_rules"):
        if raw.get(k) is not None:
            _strs(raw[k], k)
    for kind in ("artifacts", "deltas"):
        items = raw.get(kind) or []
        _need(isinstance(items, list) and all(isinstance(a, dict) for a in items), f"{kind}: objects")
        for a in items:
            for k in ("claim", "uncertainty", "channel_id", "context_update", "stream"):
                if k in a:
                    _need(isinstance(a[k], str), f"{kind}[].{k}: a string")
            for k in ("evidence", "requests"):
                if k in a:
                    _strs(a[k], f"{kind}[].{k}")
    log = raw.get("log") or []
    _need(isinstance(log, list) and all(isinstance(e, dict) for e in log), "log: objects")
    for e in log:
        _need(isinstance(e.get("event"), str) and isinstance(e.get("detail", {}), dict), "log[]: event and detail")
        _number(e.get("ts"), "log[].ts", optional=True)
    calls = raw.get("calls") or []
    _need(isinstance(calls, list) and all(isinstance(c, dict) for c in calls), "calls: objects")
    for c in calls:
        for k in ("slot", "function", "channel", "mode", "adapter"):
            _need(c.get(k) is None or isinstance(c[k], str), f"calls[].{k}: a string")
        for k in ("prompt_tokens", "completion_tokens", "latency_s"):
            _number(c.get(k), f"calls[].{k}", optional=True)
    b = raw.get("budget")
    if b is not None:
        _need(isinstance(b, dict), "budget: an object")
        for k in ("max_calls", "max_tokens", "max_seconds", "max_tokens_per_call", "elapsed"):
            _number(b.get(k), f"budget.{k}", optional=True)
        for k in ("allow_split", "allow_adapt"):
            _need(isinstance(b.get(k, True), bool), f"budget.{k}: true or false")


def _from_dict(raw: dict) -> Run:
    st = raw["state"]
    state = RunState(
        lead_id=st["lead_id"],
        slots=[_slot(s) for s in st["slots"]],
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
            started_at=time.time() - float(raw_b.get("elapsed") or 0),
        )
    w = raw.get("world")
    if w is not None:
        _need(isinstance(w, dict), "world: an object")
        m.world = World(**{k: [str(x) for x in w.get(k) or []] for k in ("existing_files", "existing_channels", "notes")})
    return m
