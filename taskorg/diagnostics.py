"""Diagnostics at run, slot, stream, and interaction level."""

from __future__ import annotations

from collections import Counter

from .run import Run


PHASES = ("context", "switch_skill", "split", "artifact", "delta", "review_open", "review_answer", "complete", "abort")


def diagnose(run: Run) -> dict:
    events = [e.event for e in run.log]
    counts = Counter(events)
    started = run.log[0].ts if run.log else 0.0
    ended = run.log[-1].ts if run.log else started
    duration = max(0.0, ended - started)

    by_slot = []
    for slot in run.state.slots:
        arts = [a for a in run.artifacts if a.channel_id == slot.channel_id] if slot.channel_id else []
        if not arts and slot.function == "lead":
            arts = [a for a in run.artifacts if a.channel_id == "lead-merge"]
        if not arts and slot.function == "verifier":
            arts = [a for a in run.artifacts if a.channel_id == "verify"]
        by_slot.append({
            "id": slot.id,
            "function": slot.function,
            "skill": slot.skill,
            "channel_id": slot.channel_id,
            "tools": list(slot.tools),
            "artifacts": len(arts),
        })

    streams = Counter(d.stream for d in run.deltas)
    interactions = []
    for e in run.log:
        kind = _kind(e.event)
        if kind:
            interactions.append({"ts": e.ts, "kind": kind, "event": e.event, "detail": _small(e.detail)})

    flags = []
    if run.open_review_ids():
        flags.append("open_reviews")
    if run.summary().get("replan_open"):
        flags.append("replan_unanswered")
    if any(e.event == "split" and not e.detail.get("gates") for e in run.log):
        flags.append("split_without_gates")
    if run.state.worker_count() > 1 and not any(d.stream == "merge" for d in run.deltas):
        flags.append("split_without_merged_results")

    tier = _tier(run)
    flags.extend(tier.get("flags") or [])
    iso = _isolation(run)
    flags = flags + iso.get("flags", [])
    auth = _authority(run)
    flags.extend(auth.get("flags") or [])
    roster = _roster(run)
    flags.extend(roster.get("flags") or [])
    return {
        "tier": tier,
        "run": {
            "id": run.id,
            "status": run.status.value,
            "duration_s": round(duration, 4),
            "events": len(run.log),
            "workers": run.state.worker_count(),
            "could_this_have_been_one": run.state.worker_count() == 0,
            "context_checked": run.state.context_sufficient,
            "method": run.state.method,
            "axes": list(run.state.axes),
        },
        "counts": dict(counts),
        "phases_seen": [p for p in PHASES if p in counts],
        "slots": by_slot,
        "streams": {
            "open": list(run.open_streams),
            "delta_counts": dict(streams),
            "deltas": len(run.deltas),
        },
        "reviews": {
            "notes": len(run.notes),
            "open": run.open_review_ids(),
            "kinds": {k: n.kind for k, n in run.notes.items()},
        },
        "cues": list(run.cues),
        "interactions": interactions,
        "performance": _performance(run),
        "isolation": iso,
        "roster": roster,
        "authority": auth,
        "adapter": getattr(run, "adapter_name", "") or next((c.get("adapter") for c in getattr(run, "calls", []) if c.get("adapter")), ""),
        "flags": flags,
        "health": "degraded" if flags else "ok",
    }


def _tier(run: Run) -> dict:
    b = getattr(run, "budget", None)
    flags = []
    if b is None:
        return {"name": "unknown", "armed": False, "flags": ["budget_missing"]}
    used_calls = len(getattr(run, "calls", []) or [])
    used_tokens = sum((c.get("prompt_tokens") or 0) + (c.get("completion_tokens") or 0) for c in getattr(run, "calls", []) or [])
    started = run.log[0].ts if run.log else 0.0
    ended = run.log[-1].ts if run.log else started
    elapsed = max(0.0, ended - started)
    workers = run.state.worker_count()
    name = getattr(b, "tier", "open")
    if name == "tight" and workers > 0:
        flags.append("tight_grew_roster")
    if name == "tight" and any(e.event == "split" for e in run.log):
        flags.append("tight_split")
    if name == "normal" and workers > 0:
        flags.append("normal_split")
    if name == "tight" and any(n.kind == "replan" for n in run.notes.values()):
        flags.append("tight_replan")
    if run.status.value == "abort" and (run.stop_reason or "").startswith("max_"):
        flags.append("budget_halt")
    remaining = {
        "calls": max(0, b.max_calls - used_calls),
        "tokens": max(0, b.max_tokens - used_tokens),
        "seconds": round(max(0.0, b.max_seconds - elapsed), 3),
    }
    return {
        "name": name,
        "armed": True,
        "allow_split": getattr(b, "allow_split", True),
        "allow_adapt": getattr(b, "allow_adapt", True),
        "caps": {
            "max_calls": b.max_calls,
            "max_tokens": b.max_tokens,
            "max_seconds": b.max_seconds,
            "max_tokens_per_call": b.max_tokens_per_call,
        },
        "used": {"calls": used_calls, "tokens": used_tokens, "seconds": round(elapsed, 3)},
        "remaining": remaining,
        "stop_reason": getattr(run, "stop_reason", ""),
        "flags": flags,
    }


def _performance(run: Run) -> dict:
    calls = list(getattr(run, "calls", []) or [])
    lat = [c.get("latency_s") or 0 for c in calls]
    pt = sum(c.get("prompt_tokens") or 0 for c in calls)
    ct = sum(c.get("completion_tokens") or 0 for c in calls)
    return {
        "calls": len(calls),
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "tokens": pt + ct,
        "latency_s_total": round(sum(lat), 4),
        "latency_s_max": round(max(lat), 4) if lat else 0,
        "by_channel": [
            {
                "channel": c.get("channel"),
                "function": c.get("function"),
                "latency_s": c.get("latency_s"),
                "prompt_tokens": c.get("prompt_tokens"),
                "completion_tokens": c.get("completion_tokens"),
            }
            for c in calls
        ],
    }


def _isolation(run: Run) -> dict:
    """Did any worker brief carry a sibling's product?

    heard_channels is computed at call time over the whole brief (packet and
    context) and survives save/load. packet is only present in memory.
    """
    workers = [c for c in getattr(run, "calls", []) or [] if c.get("function") == "worker"]
    heard: dict[str, set[str]] = {}
    unverified: set[str] = set()
    for c in workers:
        ch = c.get("channel")
        heard.setdefault(ch, set())
        if "heard_channels" not in c and "packet" not in c:
            unverified.add(ch)
        heard[ch].update(c.get("heard_channels") or [])
    channels = sorted(heard)
    for c in workers:
        packet = c.get("packet") or ""
        for other in channels:
            if other != c.get("channel") and f"channel:{other}" in packet:
                heard[c.get("channel")].add(other)
    pairs, flags = [], []
    for into in channels:
        for src in channels:
            if src == into:
                continue
            leaked = src in heard[into]
            pairs.append({"from_channel": src, "into_brief": into, "heard_sibling": leaked})
            if leaked:
                flags.append(f"isolation_leak:{src}->{into}")
    if unverified:
        flags.append("isolation_unverified")
    return {"pairs": pairs, "flags": flags, "unverified": sorted(unverified)}


def _kind(event: str) -> str | None:
    mapping = {
        "context": "context",
        "switch_skill": "roster",
        "set_roster": "roster",
        "split": "roster",
        "set_method": "method",
        "artifact": "act",
        "delta": "merge",
        "review_open": "review",
        "review_answer": "review",
        "open_stream": "stream",
        "complete": "run",
        "cue_mint": "trigger",
        "gate": "roster",
        "tool": "act",
    }
    return mapping.get(event)


def _small(detail: dict) -> dict:
    keep = {}
    for k, v in (detail or {}).items():
        if k in ("actor", "slot", "skill", "stream", "channel", "response", "id", "added", "method", "axes",
                 "channel_id", "legal", "gate", "refused", "request"):
            keep[k] = v
    return keep


TAKEOVER = ("set_roster", "spawn", "i am the lead", "take over the roster", "change the roster", "add a worker")


def _authority(run: Run) -> dict:
    flags = []
    hits = []
    for art in run.artifacts:
        blob = " ".join([art.claim, *art.evidence, art.context_update]).lower()
        found = []
        for w in TAKEOVER:
            if w not in blob:
                continue
            # Guidelines quote ("may not take over the roster") is not a hit.
            idx = blob.find(w)
            window = blob[max(0, idx - 18) : idx]
            if any(neg in window for neg in ("not ", "may not ", "cannot ", "can't ", "do not ", "don't ")):
                continue
            found.append(w)
        if found:
            hits.append({"channel": art.channel_id, "terms": found})
            flags.append(f"authority_language:{art.channel_id}")
    return {"hits": hits, "flags": flags}


def _roster(run: Run) -> dict:
    now = [s.id for s in run.state.slots]
    opened = list(getattr(run, "roster_at_start", []) or [])
    flags = []
    if opened and now != opened and run.state.worker_count() == 0:
        flags.append("roster_changed_without_workers")
    return {
        "open": opened,
        "now": now,
        "unchanged": opened == now,
        "lead": run.state.lead_id,
        "flags": flags,
    }
