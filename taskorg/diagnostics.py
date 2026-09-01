"""Diagnostics at mission, slot, net, and interaction level."""

from __future__ import annotations

from collections import Counter

from .mission import Mission


def diagnose(mission: Mission) -> dict:
    events = [e.event for e in mission.log]
    counts = Counter(events)
    started = mission.log[0].ts if mission.log else 0.0
    ended = mission.log[-1].ts if mission.log else started
    duration = max(0.0, ended - started)
    b = getattr(mission, "budget", None)
    used_calls = len(getattr(mission, "calls", []) or [])
    used_tokens = sum((c.get("prompt_tokens") or 0) + (c.get("completion_tokens") or 0) for c in getattr(mission, "calls", []) or [])
    flags = []
    if mission.open_why_ids():
        flags.append("open_why")
    if mission.summary().get("plan_wrong_open"):
        flags.append("plan_wrong_unanswered")
    workers = mission.picture.worker_count()
    name = getattr(b, "pace", "unknown") if b else "unknown"
    if name == "crawl" and workers > 0:
        flags.append("crawl_grew_who")
    if name == "crawl" and any(e.event == "split" for e in mission.log):
        flags.append("crawl_split")
    pace = {
        "name": name,
        "armed": b is not None,
        "allow_split": bool(getattr(b, "allow_split", False)) if b else False,
        "allow_adapt": bool(getattr(b, "allow_adapt", False)) if b else False,
        "caps": {
            "max_calls": getattr(b, "max_calls", None),
            "max_tokens": getattr(b, "max_tokens", None),
            "max_seconds": getattr(b, "max_seconds", None),
            "max_tokens_per_call": getattr(b, "max_tokens_per_call", None),
        } if b else {},
        "used": {"calls": used_calls, "tokens": used_tokens, "seconds": round(duration, 4)},
        "remaining": {
            "calls": max(0, (b.max_calls - used_calls)) if b else None,
            "tokens": max(0, (b.max_tokens - used_tokens)) if b else None,
            "seconds": max(0.0, (b.max_seconds - duration)) if b else None,
        },
        "stop_reason": getattr(mission, "stop_reason", ""),
        "flags": flags,
    }
    nets = Counter(d.net for d in mission.deltas)
    return {
        "pace": pace,
        "mission": {
            "id": mission.id,
            "status": mission.status.value,
            "duration_s": round(duration, 4),
            "events": len(mission.log),
            "workers": workers,
            "could_this_have_been_one": workers == 0,
            "looked": mission.picture.context_sufficient,
            "method": mission.picture.method,
            "axes": list(mission.picture.axes),
        },
        "counts": dict(counts),
        "nets": {
            "open": list(mission.open_nets),
            "delta_counts": dict(nets),
            "deltas": len(mission.deltas),
        },
        "flags": flags,
        "health": "degraded" if flags else "ok",
        "adapter": getattr(mission, "adapter_name", ""),
    }
