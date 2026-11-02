"""Does a sub-agent hand back a part the plan got wrong? The report bench measures it on its own.

With --report-up (team design part 8), a sub-agent whose part cannot be done as planned may say so with
replan:REASON, and the lead takes the part back. Whether a real model does that, or guesses, cannot be
counted from real runs: a plan that is wrong for one part is too rare. So the bench builds the parts, the
way a lead's plan hands them out for an aggregate question, and plants the error in some:

  right       the part names a company, and its sub-agent's files are that company's own notes
  look-alike  its files are the notes of the company's look-alike, which name the company only for an
              FY2025 figure
  other       its files are an unrelated company's notes

The plan error is the one a lead makes: it named the part's channel after the wrong file. The sub-agent
is told the company, and its tools open only the files the kernel measured for that channel. Only the
sub-agent's calls go to the model.

Setups:

  today      the sub-agent brief as it is by default
  report-up  the brief says it may hand the part back (Engine report_up)

Measures: wrong parts handed back, said missing, or given a figure; right parts reported or handed back;
tokens a part.
"""

from __future__ import annotations

import json
import random
import re
import statistics
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from . import atomic
from .adapters import ModelAdapter
from .budget import Budget
from .compare import DONE_WHEN, PURPOSE, task_context, trial_cost
from .errors import InvariantError
from .factory import new_run
from .gates import Assessment, Subtask
from .loop import Engine
from .memory_store import MemoryStore
from .models import GATE_ORDER, GateRecord
from .suite import Suite, Task, extract_answer, slug
from .tools import Toolbox

SETUPS: dict[str, bool] = {"today": False, "report-up": True}
KINDS = ("right", "look-alike", "other")
# Per question: two right parts, one of each wrong kind. Half the parts are wrong.
VARIANTS = (("right", 0), ("right", 1), ("look-alike", 0), ("other", 0))
TOOL_ROUNDS = 2
# Words a report uses when it says its files do not hold the figure. A rough sort; the claims are kept to read.
_MISSING = re.compile(
    r"\b(not (?:in|found|present|available|listed|included|contain\w*|mention\w*|hold\w*|have|give\w*|"
    r"report\w*|appear\w*|provided|stated)|no (?:figure|data|mention|record|revenue|information|file)\w*|"
    r"does(?:n't| not)|cannot|can't|unable|absent|missing|isn't|is not|only (?:covers|contains|has))\b",
    re.IGNORECASE,
)


@dataclass
class Part:
    kind: str
    company: str        # the company the part names
    channel: str        # the channel the plan gave it: a file's stem
    note: str           # the lead's note for the sub-agent
    true: float         # the company's FY2026 figure, in its own notes only
    planted: list[float]  # figures the sub-agent's files hold that a guess would report as the company's


@dataclass
class PartResult:
    task_id: str
    kind: str
    variant: int
    setup: str
    repeat: int
    outcome: str        # handed back | right | said missing | given a figure | failed | other
    right: bool         # a wrong part handed back, or a right part reported with its figure
    code: str
    calls: int
    tokens: int
    prompt_tokens: int
    completion_tokens: int
    tokens_estimated: bool
    latency_s: float
    said: str           # the report's claim, or the reason it handed the part back


def _quarter(task: Task) -> str:
    return re.search(r"FY2026 (Q[1-4])", task.question).group(1)


def build(suite: Suite, task: Task, kind: str, variant: int = 0) -> Part | None:
    """One part of an aggregate question, or None when the question has no company to plant this kind
    of error in (a look-alike needs a company whose look-alike is in the corpus)."""
    if task.family != "aggregate":
        raise ValueError(f"the report bench builds parts of aggregate questions, not {task.family}")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    rng = random.Random(f"{suite.seed}:{task.id}:{kind}:{variant}")
    q = _quarter(task)
    names = list(task.entities)
    if kind == "look-alike":
        paired = [n for n in names if suite.companies[n].sister]
        if not paired:
            return None
        name = rng.choice(paired)
        held = suite.companies[name].sister
        planted = [suite.companies[held].revenue[q], suite.companies[name].revenue_fy2025_q3]
    elif kind == "other":
        name = rng.choice(names)
        unrelated = [n for n in suite.companies if n != name and n != suite.companies[name].sister]
        held = rng.choice(sorted(unrelated))
        planted = [suite.companies[held].revenue[q]]
    else:
        name = rng.choice(names)
        held, planted = name, []
    return Part(kind=kind, company=name, channel=slug(held), note=f"report {name}'s FY2026 {q} revenue",
                true=suite.companies[name].revenue[q], planted=planted)


def parts(suite: Suite) -> list[tuple[Task, int, Part]]:
    """Every part the bench hands out: VARIANTS for each aggregate question, in task order."""
    out = []
    for task in suite.tasks:
        if task.family != "aggregate":
            continue
        for kind, variant in VARIANTS:
            part = build(suite, task, kind, variant)
            if part is not None:
                out.append((task, variant, part))
    return out


def _states(text: str, value: float) -> bool:
    return re.search(rf"(?<![\d.]){re.escape(f'{value:.1f}')}(?!\d)", text) is not None


def outcome(part: Part, said: str, handed_back: bool, code: str) -> str:
    if handed_back:
        return "handed back"
    if code:
        return "failed"
    if part.kind == "right":
        return "right" if _states(said, part.true) else "other"
    # The answer line is what the part reports, whatever else the report says about its files. On Haiku,
    # "$72.9 million, per the wrong file; my channel holds no files for the others" read as missing without it.
    if any(_states(extract_answer(said) or "", v) for v in part.planted):
        return "given a figure"
    if _MISSING.search(said):
        return "said missing"
    if any(_states(said, v) for v in part.planted):
        return "given a figure"
    return "other"


def part_trial(
    task: Task,
    part: Part,
    setup: str,
    adapter: ModelAdapter,
    corpus_dir: Path,
    *,
    budget: Budget,
    variant: int = 0,
    repeat: int = 0,
) -> PartResult:
    """One part: a fresh run split the way the plan split it, then the sub-agent's calls alone."""
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(Path(tmp))
        run = new_run(f"report-{task.id}-{part.kind}-{variant}-r{repeat}", goal=task.question, purpose=PURPOSE,
                      done_when=DONE_WHEN)
        run.state.success_criteria = ["ANSWER:"]
        engine = Engine(store, adapter=adapter, budget=budget, toolbox=Toolbox(roots=[corpus_dir]),
                        max_tool_rounds=TOOL_ROUNDS, report_up=SETUPS[setup])
        engine._arm(run)
        lead = run.state.lead_id
        context = task_context(task)
        run.update_context(lead, context)
        store.remember_working(run.id, "context", context)
        subtask = Subtask(part.channel, part.note, skill="retrieve")
        legal = Assessment(subtask, GateRecord(False, True, part.note, True, part.channel, GATE_ORDER))
        run.set_method(lead, f"sub-agents: {part.channel}", ["parallel", "fan_in"])
        added = engine._staff(run, [legal])
        stopped = ""
        started = time.perf_counter()
        try:
            engine._run_workers(run, added, run.state.context, notes={part.channel: part.note})
        except InvariantError as e:  # a stop the team does not absorb, such as the budget
            stopped = e.code
        latency = time.perf_counter() - started
    reported = [e.detail for e in run.log if e.event == "part_reported"]
    failed = [e.detail for e in run.log if e.event == "part_failed"]
    reports = [a for a in run.artifacts if a.channel_id == part.channel]
    code = str(failed[0].get("code", "")) if failed else stopped
    said = reported[0]["reason"] if reported else (reports[-1].claim if reports else (failed[0].get("error", "") if failed else ""))
    result = outcome(part, said, bool(reported), code)
    prompt = sum(c.get("prompt_tokens") or 0 for c in run.calls)
    completion = sum(c.get("completion_tokens") or 0 for c in run.calls)
    return PartResult(
        task_id=task.id, kind=part.kind, variant=variant, setup=setup, repeat=repeat, outcome=result,
        right=(result == "handed back") if part.kind != "right" else (result == "right"),
        code=code, calls=len(run.calls), tokens=prompt + completion, prompt_tokens=prompt,
        completion_tokens=completion, tokens_estimated=any(c.get("tokens_estimated") for c in run.calls),
        latency_s=round(latency, 3), said=str(said)[:240],
    )


def run_bench(
    suite: Suite,
    adapter_factory: Callable[[], ModelAdapter],
    *,
    setups: tuple[str, ...] = tuple(SETUPS),
    repeats: int = 1,
    budget_factory: Callable[[], Budget],
    corpus_dir: Path | None = None,
    progress: Callable[[str], None] | None = None,
    stop_when: Callable[[list[PartResult]], str] | None = None,
) -> list[PartResult]:
    """Every part under every setup, setups interleaved so endpoint drift hits them alike. A stop_when
    reason, or Ctrl-C, ends it before the next part; the parts already run are returned."""
    results: list[PartResult] = []
    items = parts(suite)
    total = len(items) * len(setups) * repeats
    with tempfile.TemporaryDirectory() as tmp:
        root = suite.write_corpus(corpus_dir or Path(tmp) / "corpus")
        try:
            for r in range(repeats):
                for task, variant, part in items:
                    for setup in setups:
                        reason = stop_when(results) if stop_when else ""
                        if reason:
                            if progress:
                                progress(f"stopped after {len(results)} of {total} parts: {reason}")
                            return results
                        res = part_trial(task, part, setup, adapter_factory(), root, budget=budget_factory(),
                                         variant=variant, repeat=r)
                        results.append(res)
                        if progress:
                            mark = "ok " if res.right else "x  "
                            progress(f"[{len(results)}/{total}] {mark}{setup:<9} {task.id:<12} {part.kind:<10} "
                                     f"{res.outcome:<14} {res.calls} calls {res.tokens / 1000:>5.1f}k tok "
                                     f"{res.latency_s:>5.1f}s{(' ' + res.code) if res.code else ''}")
        except KeyboardInterrupt:
            if progress:
                progress(f"interrupted after {len(results)} of {total} parts; the part in progress is not counted")
    return results


def _rate(hits: int, n: int) -> float | None:
    return round(hits / n, 3) if n else None


def summarize(results: list[PartResult], *, price_in: float | None = None, price_out: float | None = None) -> dict:
    out = {}
    for setup in dict.fromkeys(r.setup for r in results):
        rows = [r for r in results if r.setup == setup]
        wrong = [r for r in rows if r.kind != "right"]
        right = [r for r in rows if r.kind == "right"]
        block = {
            "n": len(rows),
            "wrong_handed_back": _rate(sum(r.outcome == "handed back" for r in wrong), len(wrong)),
            "wrong_said_missing": _rate(sum(r.outcome == "said missing" for r in wrong), len(wrong)),
            "wrong_given_a_figure": _rate(sum(r.outcome == "given a figure" for r in wrong), len(wrong)),
            "by_kind": {k: _rate(sum(r.outcome == "handed back" for r in wrong if r.kind == k), sum(r.kind == k for r in wrong))
                        for k in KINDS[1:] if any(r.kind == k for r in wrong)},
            "right_reported": _rate(sum(r.outcome == "right" for r in right), len(right)),
            "right_handed_back": _rate(sum(r.outcome == "handed back" for r in right), len(right)),
            "failed": sum(r.outcome == "failed" for r in rows),
            "other": sum(r.outcome == "other" for r in rows),
            "tokens_mean": round(statistics.mean(r.tokens for r in rows)),
            "tokens_estimated": any(r.tokens_estimated for r in rows),
        }
        if price_in is not None and price_out is not None:
            block["cost_total"] = round(sum(trial_cost(r, price_in, price_out) for r in rows), 4)
        out[setup] = block
    return {"setups": out}


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0%}"


def render(summary: dict) -> str:
    blocks = summary["setups"]
    has_cost = any("cost_total" in v for v in blocks.values())
    lines = ["## Report bench", "",
             "| setup | wrong handed back | look-alike | other | wrong said missing | wrong given a figure "
             "| right reported | right handed back | tokens/part |" + (" cost |" if has_cost else ""),
             "|---|---|---|---|---|---|---|---|---|" + ("---|" if has_cost else "")]
    for setup, v in blocks.items():
        kinds = v["by_kind"]
        row = (f"| {setup} | {_pct(v['wrong_handed_back'])} | {_pct(kinds.get('look-alike'))} | {_pct(kinds.get('other'))} | "
               f"{_pct(v['wrong_said_missing'])} | {_pct(v['wrong_given_a_figure'])} | {_pct(v['right_reported'])} | "
               f"{_pct(v['right_handed_back'])} | {v['tokens_mean']:,} |")
        if has_cost:
            row += f" ${v.get('cost_total', 0):.4f} |"
        lines.append(row)
    if any(v["failed"] or v["other"] for v in blocks.values()):
        lines += ["", "Parts that failed, or whose report the bench could not sort: "
                  + ", ".join(f"{s} {v['failed']} failed, {v['other']} unsorted" for s, v in blocks.items())]
    if any(v.get("tokens_estimated") for v in blocks.values()):
        lines += ["", "Token counts are estimated (the adapter reported no usage)."]
    return "\n".join(lines) + "\n"


def save(path: Path, *, config: dict, results: list[PartResult], summary: dict) -> Path:
    path = Path(path)
    atomic.write_text(path, json.dumps({"config": config, "summary": summary, "results": [asdict(r) for r in results]}, indent=2))
    return path
