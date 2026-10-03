"""Diagnostics at mission, slot, net, and interaction level."""

from __future__ import annotations

from collections import Counter

from .mission import Mission


PHASES = ("look", "slide", "split", "artifact", "delta", "why_submit", "why_respond", "complete", "abort")


def diagnose(mission: Mission) -> dict:
    events = [e.event for e in mission.log]
    counts = Counter(events)
    started = mission.log[0].ts if mission.log else 0.0
    ended = mission.log[-1].ts if mission.log else started
    duration = max(0.0, ended - started)

    by_slot = []
    for slot in mission.picture.slots:
        arts = [a for a in mission.artifacts if a.channel_id == slot.channel_id] if slot.channel_id else []
        if not arts and slot.function == "head":
            arts = [a for a in mission.artifacts if a.channel_id == "head-integrate"]
        if not arts and slot.function == "verifier":
            arts = [a for a in mission.artifacts if a.channel_id == "verify"]
        by_slot.append({
            "id": slot.id,
            "function": slot.function,
            "skill": slot.skill,
            "channel_id": slot.channel_id,
            "tools": list(slot.tools),
            "artifacts": len(arts),
        })

    nets = Counter(d.net for d in mission.deltas)
    interactions = []
    for e in mission.log:
        kind = _kind(e.event)
        if kind:
            interactions.append({"ts": e.ts, "kind": kind, "event": e.event, "detail": _small(e.detail)})

    flags = []
    if mission.open_why_ids():
        flags.append("open_why")
    if mission.summary().get("plan_wrong_open"):
        flags.append("plan_wrong_unanswered")
    if any(e.event == "split" and not e.detail.get("gates") for e in mission.log):
        flags.append("split_without_gates")
    if mission.picture.worker_count() > 1 and not any(d.net == "element" for d in mission.deltas):
        flags.append("split_without_element_deltas")

    pace = _pace(mission)
    flags.extend(pace.get("flags") or [])
    iso = _isolation(mission)
    flags = flags + iso.get("flags", [])
    auth = _authority(mission)
    flags.extend(auth.get("flags") or [])
    who = _who(mission)
    flags.extend(who.get("flags") or [])
    return {
        "pace": pace,
        "mission": {
            "id": mission.id,
            "status": mission.status.value,
            "duration_s": round(duration, 4),
            "events": len(mission.log),
            "workers": mission.picture.worker_count(),
            "could_this_have_been_one": mission.picture.worker_count() == 0,
            "looked": mission.picture.context_sufficient,
            "method": mission.picture.method,
            "axes": list(mission.picture.axes),
        },
        "counts": dict(counts),
        "phases_seen": [p for p in PHASES if p in counts],
        "slots": by_slot,
        "nets": {
            "open": list(mission.open_nets),
            "delta_counts": dict(nets),
            "deltas": len(mission.deltas),
        },
        "why": {
            "notes": len(mission.notes),
            "open": mission.open_why_ids(),
            "kinds": {k: n.kind for k, n in mission.notes.items()},
        },
        "cues": list(mission.cues),
        "interactions": interactions,
        "performance": _performance(mission),
        "isolation": iso,
        "who": who,
        "authority": auth,
        "adapter": getattr(mission, "adapter_name", "") or next((c.get("adapter") for c in getattr(mission, "calls", []) if c.get("adapter")), ""),
        "flags": flags,
        "health": "degraded" if flags else "ok",
    }


def _pace(mission: Mission) -> dict:
    b = getattr(mission, "budget", None)
    flags = []
    if b is None:
        return {"name": "unknown", "armed": False, "flags": ["budget_missing"]}
    used_calls = len(getattr(mission, "calls", []) or [])
    used_tokens = sum((c.get("prompt_tokens") or 0) + (c.get("completion_tokens") or 0) for c in getattr(mission, "calls", []) or [])
    started = mission.log[0].ts if mission.log else 0.0
    ended = mission.log[-1].ts if mission.log else started
    elapsed = max(0.0, ended - started)
    workers = mission.picture.worker_count()
    name = getattr(b, "pace", "run")
    if name == "crawl" and workers > 0:
        flags.append("crawl_grew_who")
    if name == "crawl" and any(e.event == "split" for e in mission.log):
        flags.append("crawl_split")
    if name == "walk" and workers > 0:
        flags.append("walk_split")
    if name == "crawl" and any(n.kind == "plan_wrong" for n in mission.notes.values()):
        flags.append("crawl_adapt")
    if mission.status.value == "abort" and (mission.stop_reason or "").startswith("max_"):
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
        "stop_reason": getattr(mission, "stop_reason", ""),
        "flags": flags,
    }


def _performance(mission: Mission) -> dict:
    calls = list(getattr(mission, "calls", []) or [])
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


def _isolation(mission: Mission) -> dict:
    """Did any worker brief carry a sibling's product?

    heard_channels is computed at call time over the whole brief (packet and
    picture) and survives save/load. packet is only present in memory.
    """
    workers = [c for c in getattr(mission, "calls", []) or [] if c.get("function") == "worker"]
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
        "look": "where",
        "slide": "who",
        "write_who": "who",
        "split": "who",
        "set_how": "how",
        "artifact": "act",
        "delta": "element",
        "why_submit": "up",
        "why_respond": "up",
        "write_net": "net",
        "complete": "mission",
        "cue_mint": "when",
        "gate": "who",
        "tool": "act",
    }
    return mapping.get(event)


def _small(detail: dict) -> dict:
    keep = {}
    for k, v in (detail or {}).items():
        if k in ("actor", "slot", "skill", "net", "channel", "response", "id", "added", "method", "axes",
                 "channel_id", "legal", "gate", "refused", "request"):
            keep[k] = v
    return keep


SEIZE = ("write_who", "spawn", "i am the head", "take over the roster", "change who", "add a worker")


def _authority(mission: Mission) -> dict:
    flags = []
    hits = []
    for art in mission.artifacts:
        blob = " ".join([art.claim, *art.evidence, art.delta_to_picture]).lower()
        found = []
        for w in SEIZE:
            if w not in blob:
                continue
            # Doctrine quote ("may not take over the roster") is not a hit.
            idx = blob.find(w)
            window = blob[max(0, idx - 18) : idx]
            if any(neg in window for neg in ("not ", "may not ", "cannot ", "can't ", "do not ", "don't ")):
                continue
            found.append(w)
        if found:
            hits.append({"channel": art.channel_id, "terms": found})
            flags.append(f"authority_language:{art.channel_id}")
    return {"hits": hits, "flags": flags}


def _who(mission: Mission) -> dict:
    now = [s.id for s in mission.picture.slots]
    opened = list(getattr(mission, "who_open", []) or [])
    flags = []
    if opened and now != opened and mission.picture.worker_count() == 0:
        flags.append("who_changed_without_workers")
    return {
        "open": opened,
        "now": now,
        "unchanged": opened == now,
        "head": mission.picture.who_head_id,
        "flags": flags,
    }
