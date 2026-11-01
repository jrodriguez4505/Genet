"""The lead knows its members (team design part 7): a card for each position the lead can staff, and
that position's record from past runs.

A position is a skill and the model that fills it. Agents are copies of one model, so the record is kept
by position, never by agent. The kernel writes cards and records from its own tables and the run's
record, never from model text. The cards go in the lead's plan brief as a table of fixed size, one row a
skill. They show counts, not scores, and the gates never read them.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from .errors import InvariantError
from .models import SKILL_TOOLS, SKILLS, Status
from .tools import RUNNABLE

# A position's record shows only after this many runs, so one bad run does not steer the lead.
MIN_RUNS = 3
# Positions kept in the store; the least recently updated go first.
MAX_POSITIONS = 64
# Stored counts are clamped, so a damaged file cannot carry a huge number into a brief.
COUNT_CAP = 10**9
MODEL_CHARS = 60
_CODE = re.compile(r"^[A-Z_]{1,16}$")
_COUNTS = ("runs", "parts", "done", "verified", "handed_back", "calls", "tokens")

CARDS_HEAD = (
    "MEMBERS. Each position you can staff is a skill and the model that fills it. The kernel writes this table "
    "from its own record: what each position can open, the most calls one part may take, what one of its calls "
    "has cost, and, once a position has {min_runs} runs, its counts from them. The gates judge your proposal "
    "as they always do."
)
CARDS_COLUMNS = "| skill | tools | opens files | calls a part | model | tokens a call | past runs |"


@dataclass
class Record:
    """One position's counts, summed over the runs that staffed it."""

    skill: str
    model: str
    runs: int = 0         # runs that staffed this position
    parts: int = 0        # parts it was given
    done: int = 0         # parts whose report the lead accepted
    verified: int = 0     # of those, parts in a run whose product the verifier passed
    failed: dict[str, int] = field(default_factory=dict)  # parts whose sub-agent failed, by code
    handed_back: int = 0  # parts its sub-agent handed back as planned wrong (part 8)
    calls: int = 0
    tokens: int = 0

    @property
    def covered(self) -> int:
        """Parts the lead had to cover: failed or handed back."""
        return sum(self.failed.values()) + self.handed_back

    def add(self, other: Record) -> None:
        for name in _COUNTS:
            setattr(self, name, min(COUNT_CAP, getattr(self, name) + getattr(other, name)))
        for code, n in other.failed.items():
            self.failed[code] = min(COUNT_CAP, self.failed.get(code, 0) + n)


def _count(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("not a count")
    return min(value, COUNT_CAP)


def parse(raw) -> list[Record]:
    """Records as the store holds them. Anything else is a damaged file: a clean STORE error."""
    try:
        if not isinstance(raw, list):
            raise ValueError("not a list")
        out = []
        for entry in raw[:MAX_POSITIONS]:
            skill, model, failed = entry["skill"], entry["model"], entry.get("failed", {})
            if skill not in SKILLS or not isinstance(model, str) or not 0 < len(model) <= MODEL_CHARS:
                raise ValueError("not a position")
            if not isinstance(failed, dict) or not all(isinstance(k, str) and _CODE.fullmatch(k) for k in failed):
                raise ValueError("not failure counts")
            out.append(Record(skill, model, **{n: _count(entry.get(n, 0)) for n in _COUNTS},
                              failed={k: _count(v) for k, v in failed.items()}))
        return out
    except (TypeError, KeyError, ValueError, AttributeError) as e:
        raise InvariantError("STORE", f"position records are damaged: {type(e).__name__}") from e


def _name(model_of: Callable[[str], str], skill: str) -> str:
    return str(model_of(skill) or "")[:MODEL_CHARS] or "unknown"


def from_run(run, model_of: Callable[[str], str]) -> list[Record]:
    """The counts one run adds, one record per position it staffed. From the run's record only."""
    workers = {s.id: s for s in run.state.slots if s.function == "worker"}
    if not workers:
        return []
    failed = {e.detail.get("slot"): e.detail.get("code") for e in run.log if e.event == "part_failed"}
    handed = {e.detail.get("slot") for e in run.log if e.event == "part_reported"}
    reported = {e.detail.get("channel") for e in run.log if e.event == "artifact"}
    verified = run.status == Status.COMPLETE
    out: dict[tuple[str, str], Record] = {}
    for slot in workers.values():
        key = (slot.skill, _name(model_of, slot.skill))
        rec = out.setdefault(key, Record(*key, runs=1))
        rec.parts += 1
        if slot.id in failed:
            code = str(failed[slot.id] or "")
            code = code if _CODE.fullmatch(code) else "OTHER"
            rec.failed[code] = rec.failed.get(code, 0) + 1
        elif slot.id in handed:
            rec.handed_back += 1
        elif slot.channel_id in reported:
            rec.done += 1
            rec.verified += int(verified)
    for call in run.calls:
        slot = workers.get(call.get("slot"))
        if slot is not None:
            rec = out[(slot.skill, _name(model_of, slot.skill))]
            rec.calls += 1
            rec.tokens += int(call.get("prompt_tokens") or 0) + int(call.get("completion_tokens") or 0)
    return list(out.values())


def merge(old: list[Record], new: list[Record]) -> list[dict]:
    """The store's records with one run's added, the positions it touched first, at most MAX_POSITIONS."""
    kept = {(r.skill, r.model): r for r in old}
    touched: dict[tuple[str, str], Record] = {}
    for rec in new:
        key = (rec.skill, rec.model)
        base = touched.get(key) or kept.pop(key, None) or Record(*key)
        base.add(rec)
        touched[key] = base
    return [asdict(r) for r in (list(touched.values()) + list(kept.values()))[:MAX_POSITIONS]]


def _past(rec: Record | None) -> str:
    if rec is None or rec.runs < MIN_RUNS:
        return f"fewer than {MIN_RUNS} runs"
    failed = sum(rec.failed.values())
    codes = ", ".join(f"{k} {v}" for k, v in sorted(rec.failed.items()) if v)
    return (f"{rec.runs} runs: {rec.parts} parts, {rec.done} done, {rec.verified} verified, "
            f"{failed} failed{f' ({codes})' if codes else ''}, {rec.handed_back} handed back, "
            f"{rec.covered} covered by the lead")


def cards(records: list[Record], model_of: Callable[[str], str], calls_of: Callable[[str], int]) -> str:
    """The table for the plan brief: one row for each skill, filled by the model the run would use."""
    rows = [CARDS_HEAD.format(min_runs=MIN_RUNS), CARDS_COLUMNS, "|---|---|---|---|---|---|---|"]
    for skill in SKILLS:
        model = _name(model_of, skill)
        rec = next((r for r in records if r.skill == skill and r.model == model), None)
        tools = SKILL_TOOLS.get(skill, ())
        opens = "yes" if any(t in RUNNABLE for t in tools) else "no"
        calls = calls_of(skill)
        cost = f"about {rec.tokens // rec.calls:,}" if rec and rec.calls else "not measured yet"
        rows.append(f"| {skill} | {', '.join(tools)} | {opens} | {'up to ' if calls > 1 else ''}{calls} | {model} "
                    f"| {cost} | {_past(rec)} |")
    return "\n".join(rows)


def shown(records: list[Record], model_of: Callable[[str], str]) -> list[str]:
    """The skills whose counts the table shows, for the run's record."""
    return [r.skill for r in records if r.runs >= MIN_RUNS and r.model == _name(model_of, r.skill)]
