"""Shared ownership: a blameless review of what went wrong, and the lessons it leaves.

When a run has a failure, the kernel writes a review from the run's record: event codes, gate
verdicts, criteria misses, which parts merged and which failed. A review names what failed,
which parts contributed and what the team did about it. It does not single out an agent: the
outcome is the team's.

Nothing in a review is copied from model text. A model's words are untrusted, and each review
can leave lessons in the shared guidelines that every later brief carries, so a lesson is always
one of the fixed sentences below, chosen by the kind of failure.
"""

from __future__ import annotations

from .errors import InvariantError

LESSONS = {
    "schema": "Reply with only the JSON object the brief asks for: claim, evidence, uncertainty, "
              "channel_id, context_update and requests.",
    "criteria": "Show every success criterion in the product itself, word for word. "
                "The verifier does not count its own evidence.",
    "merge": "Merge every sub-agent's result into the product before it goes to the verifier.",
    "review_open": "Answer every open review before the product goes to the verifier.",
    "verdict": "Check the product against the goal and the done-when condition before it goes to the verifier.",
    "calls": "Plan within the call budget: propose fewer sub-tasks, and use fewer tool rounds when calls are few.",
    "tokens": "Keep briefs and replies short, and read only what the task needs.",
    "seconds": "Stay within the time budget: fewer tool rounds and smaller reads.",
    "brief_size": "Read less per round: retrieve the lines you need before reading whole files.",
    "call_size": "Keep each reply, and each round's reads, within one call's limit.",
    "tools": "Use only the tools the brief lists for your skill.",
    "roster": "Do not try to change the roster. Propose sub-tasks; the gates decide.",
    "authority": "Leave changes to the roster, context, method and reviews to the lead.",
}

_WORLD = {
    "world: workers exist but merged no results": "merge",
    "world: a review is still open": "review_open",
}


def _stop(code: str, reason: str) -> tuple[str, str | None] | None:
    """What a halt says, as (what failed, lesson key). Reasons used here are the kernel's own text."""
    if code == "VERIFY":
        return None  # the verifier's misses are reviewed from their own record
    if code == "BUDGET":
        if "not sent" in reason:
            return "a brief was too large to send", "brief_size"
        if reason.startswith("max_tokens_per_call"):
            return "a call went over the per-call token limit", "call_size"
        for cap, key in (("max_calls", "calls"), ("max_tokens", "tokens"), ("max_seconds", "seconds")):
            if reason.startswith(cap):
                return f"the run reached its {cap.replace('max_', '')} budget", key
        return "the budget tier did not allow the method", None
    if code == "TOOLS":
        return "an agent asked for a tool its skill does not allow", "tools"
    if code == "ROSTER":
        return "an agent tried to change the roster", "roster"
    if code.startswith("INV-"):
        return f"a kernel rule was broken ({code})", "authority"
    if code == "SCHEMA":
        return "the lead's reply was not the artifact schema", "schema"
    if code == "LIVE":
        return "a call to the model endpoint failed", None
    return f"the run stopped ({code})", None


def part_statuses(run) -> dict[str, str]:
    """Each part of the work and what became of it, from the record."""
    merged = {d.channel_id for d in run.deltas if d.stream == "merge"}
    failed = {e.detail.get("channel"): e.detail.get("code") for e in run.log if e.event == "part_failed"}
    covered = any(c.get("function") == "lead" and c.get("mode") == "integrate" for c in run.calls)
    parts: dict[str, str] = {}
    for slot in run.state.slots:
        if slot.function != "worker" or not slot.channel_id:
            continue
        ch = slot.channel_id
        if ch in failed:
            parts[ch] = f"failed ({failed[ch]}); " + ("covered by the lead" if covered else "not covered: the run stopped first")
        else:
            parts[ch] = "merged" if ch in merged else "not finished: the run stopped first"
    for e in run.log:
        d = e.detail
        if e.event == "gate" and not d.get("legal") and d.get("gate") in ("should_we", "could_we") and d.get("channel_id") not in parts:
            parts[d["channel_id"]] = "no sub-agent; " + ("covered by the lead" if covered else "not covered")
    return parts


def team_review(run, error: BaseException | None) -> dict | None:
    """The review, or None when nothing failed. An operator's Ctrl-C is not a team failure."""
    if isinstance(error, KeyboardInterrupt):
        return None
    failed: list[str] = []
    keys: list[str] = []

    def note(what: str, key: str | None) -> None:
        failed.append(what)
        if key and key not in keys:
            keys.append(key)

    for e in run.log:
        if e.event == "part_failed":
            code = e.detail.get("code")
            if code == "SCHEMA":
                note(f"the sub-agent for {e.detail.get('channel')} returned a reply that was not the artifact schema", "schema")
            else:
                note(f"the model call for {e.detail.get('channel')}'s sub-agent failed ({code})", None)
        elif e.event == "verify_failed":
            n = len(e.detail.get("misses") or [])
            world = list(e.detail.get("world_misses") or [])
            note("the verifier did not pass the product" + (f": {n} success criteria missing" if n else ""),
                 "criteria" if n else None)
            for w in world:
                note(f"the verifier found: {w}", _WORLD.get(w, "verdict"))
    if error is not None:
        if isinstance(error, InvariantError):
            stop = _stop(error.code, error.message)
            if stop:
                note(*stop)
        else:
            note(f"the run crashed ({type(error).__name__})", None)
    if not failed:
        return None

    done: list[str] = []
    for ch, status in part_statuses(run).items():
        if status.startswith("failed") and "covered by the lead" in status:
            done.append(f"the lead covered {ch}")
    if any(n.kind == "replan" and n.response == "CHANGE_METHOD" for n in run.notes.values()):
        done.append("the lead reworked the product once")
    done.append("the product was verified" if run.status.value == "complete" else "the run stopped")
    return {
        "outcome": run.status.value,
        "what_failed": failed,
        "parts": part_statuses(run),
        "what_was_done": done,
        "lessons": [LESSONS[k] for k in keys],
    }
