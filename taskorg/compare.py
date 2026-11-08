"""Side by side: does the gated split beat one agent, or an always-split crew?

Three strategies run the same tasks with the same model, the same tools, the
same budget and tool rounds, the same verify-and-adapt step and the same
concurrency. Only the task organization differs:

  single   one agent works the task; no planning call
  always   crew style: the lead always decomposes and every subtask gets a worker
  genet    the lead proposes sub-agents; the gates judge them (Engine.run_task)

genet-stated and genet-cards are variants of genet: the lead's reasons accepted as stated, and the lead
shown a card for each position it can staff (team design part 7).

The claim under test: genet matches the better baseline's accuracy at close to
single-agent cost. The report shows where it does and where it does not.
"""

from __future__ import annotations

import functools
import json
import re
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import atomic, checks
from .adapters import ModelAdapter
from .budget import Budget
from .errors import InvariantError
from .factory import new_run
from .gates import Assessment, Subtask, World, _could_we
from .loop import Engine
from .memory_store import MemoryStore
from .run import Run
from .models import GATE_ORDER, MAX_WORKERS, SKILLS, GateRecord
from .subtasks import parse_proposals
from .suite import Suite, Task, extract_answer, grade, slug
from .tools import Toolbox

CONTEXT = (
    # The example is a company with no look-alike: one with a sister primed readers to map
    # Halvorsen Freight Labs to halvorsen-freight.md.
    "The workspace holds FY2026 operating notes, one markdown file per company, named after its full name "
    "(for example orbrook.md for Orbrook). "
    "Figures are written in prose and the notes contain prior-year figures and look-alike company names. "
    "FY2026 is calendar 2026: Q1 is January to March, Q2 April to June, Q3 July to September, Q4 October to December. "
    "Use the files; do not guess."
)
PURPOSE = "Answer exactly from the notes. End the product with ANSWER: <value>"
DONE_WHEN = "The product ends with 'ANSWER: <value>': a number for amounts, a company name for which-questions."

DECOMPOSE_BRIEF = (
    "PLAN. You lead a crew. Break the work into 2 to 4 subtasks and give each its own worker. "
    "For each, add one request in the form subtask:CHANNEL@SKILL=WHAT_THE_WORKER_DOES, for example "
    "subtask:acme@retrieve=report Acme's FY2026 Q2 revenue from acme.md. CHANNEL is a short name of letters, "
    "digits and hyphens, one per worker: for a worker that reads one file, that file's name without its "
    "extension; never lead, which is yours. SKILL is one of {skills}. "
    "A worker that must search or read the workspace needs skill retrieve. "
    "claim: your plan in one or two sentences."
)


# The note on naming a group's files, in the crew brief's own words.
CREW_GROUP_NOTE = (
    " There can be at most {workers} workers. For a worker that reads several files, name each file in "
    "WHAT_THE_WORKER_DOES, for example subtask:north-group@retrieve=report Q2 revenue from north.md and south.md: "
    "the kernel measures a worker's part by the files it names, and the worker can open only those."
)


def task_context(task: Task) -> str:
    """The shared context, plus the figures already filed for this question. They are in the context, so
    every agent has them, and a sub-agent for one of them would repeat finished work."""
    if not task.filed:
        return CONTEXT
    q = re.search(r"FY2026 (Q[1-4])", task.question).group(1)
    done = "; ".join(f"{slug(n)} revenue {q} = {v:.1f} ({n}, $ millions)" for n, v in task.filed.items())
    return CONTEXT + f" Already filed and checked for this question: {done}. Their notes need no second reading."


class SingleAgent(Engine):
    """Baseline: one agent, no planning call, never splits."""

    def _propose(self, run: Run, again: str = "") -> list[Subtask]:
        return []


class AlwaysSplit(Engine):
    """Baseline: crew style. Always decompose; staff every usable subtask without judging it."""

    min_split = 1

    def _propose(self, run: Run, again: str = "") -> list[Subtask]:
        lead = run.state.lead_id
        run.switch_skill(lead, lead, "reason", "decompose into sub-tasks for the crew")
        plan = self._act(run, self._brief(run, "lead", extra=self._plan_brief(run), mode="plan"))
        run.accept_artifact(plan)
        return parse_proposals(plan.requests)

    def _plan_brief(self, run: Run) -> str:
        return DECOMPOSE_BRIEF.format(skills="|".join(SKILLS))

    def _judge(self, run: Run, subtasks: list[Subtask]) -> list[Assessment]:
        """No gates. Only what the kernel cannot run is dropped: bad ids, repeats, past the worker cap."""
        out, seen, staffed = [], set(), 0
        for subtask in subtasks:
            failure = subtask.named_failure.strip() or "baseline: always split"
            a = Assessment(subtask, GateRecord(False, True, failure, True, subtask.channel_id, GATE_ORDER))
            problem = _could_we(subtask)
            # Refused, not dropped: run_task gives the lead every part no sub-agent took, as it does for genet.
            if subtask.channel_id in seen:
                a.refuse("can_someone_else", f"channel {subtask.channel_id} proposed twice")
            elif problem:
                a.refuse("could_we", problem)
            elif staffed >= self.max_workers:
                a.refuse("could_we", "worker cap: no room for this sub-agent")
            else:
                staffed += 1
            seen.add(subtask.channel_id)
            run._record("gate", a.as_dict() | {"policy": "always-split"})
            out.append(a)
        return out


class ToldCrew(AlwaysSplit):
    """The crew, told what genet's lead is told about size. Still no gates: it always splits, and staffs what it
    proposes. Without this, a comparison on work that does not fit one call is partly a comparison of the notes."""

    def _plan_brief(self, run: Run) -> str:
        base = super()._plan_brief(run)
        return base + self._size_note(run, base, group=CREW_GROUP_NOTE)


class FixedSplit(AlwaysSplit):
    """The agent-count sweep: the kernel splits the files the question names into `parts` groups, as even as it can,
    one sub-agent each, and the lead merges what they report. No planning call and no gates, so the number of parts
    is the one thing that differs between arms. One part is the single baseline, so split-N starts at 2."""

    def __init__(self, *args, parts: int = 2, **kwargs):
        super().__init__(*args, max_workers=parts, **kwargs)
        self.parts = parts

    def _propose(self, run: Run, again: str = "") -> list[Subtask]:
        files = checks.named_in(run.state.goal, self.toolbox.shown_files())
        n = max(1, min(self.parts, len(files)))
        size, extra = divmod(len(files), n)
        out, i = [], 0
        for k in range(n):
            group = files[i:i + size + (k < extra)]
            i += len(group)
            named = ", ".join(group[:-1]) + (" and " if len(group) > 1 else "") + group[-1] if group else ""
            out.append(Subtask(channel_id=f"part-{k + 1:02d}", skill="retrieve",
                               named_failure=f"report what the goal asks for from {named}"))
        run._record("fixed_split", {"parts": n, "files": len(files)})
        return out


SWEEP = (2, 4, 10, 20)
CACHE_WRITE, CACHE_READ = 1.25, 0.1  # of the input price, for prompt cache writes (five-minute entries) and reads  # the parts compare's split-N strategies use

# genet uses the measured "should we"; genet-stated accepts the lead's reasons, for comparison.
BASELINES = ("single", "always")
STRATEGIES: dict[str, Callable[..., Engine]] = {
    "single": SingleAgent,
    "always": AlwaysSplit,
    "always-told": ToldCrew,
    "genet": Engine,
    "genet-stated": functools.partial(Engine, split_policy="stated"),
    "genet-cards": functools.partial(Engine, cards=True),
} | {f"split-{n}": functools.partial(FixedSplit, parts=n) for n in SWEEP}


@dataclass
class TrialResult:
    task_id: str
    family: str
    strategy: str
    repeat: int
    expected: str
    answer: str | None
    correct: bool        # delivered (run complete) and right
    answer_right: bool   # last product right, whether or not the run completed
    status: str
    code: str
    calls: int
    tokens: int
    prompt_tokens: int
    completion_tokens: int
    tokens_estimated: bool
    latency_s: float
    workers: int
    proposed: int = 0    # parts the gates judged
    refused: int = 0     # of those, parts the gates refused
    covered: int = 0     # parts whose sub-agent failed or handed them back, for the lead to cover
    cache_write_tokens: int = 0  # of prompt_tokens, written to a prompt cache (1.25 times the input price)
    cache_read_tokens: int = 0   # of prompt_tokens, read from one (a tenth of it)
    # model -> [prompt, completion, cache write, cache read] tokens, for a team that mixes models
    by_model: dict = field(default_factory=dict)


def _last_product(run: Run) -> str:
    products = [a for a in run.artifacts if a.channel_id == "lead-merge"]
    return products[-1].claim if products else ""


def run_trial(
    task: Task,
    strategy: str,
    adapter: ModelAdapter,
    corpus_dir: Path,
    *,
    budget: Budget,
    tool_rounds: int = 3,
    repeat: int = 0,
    store_root: Path | None = None,
    verify: dict | None = None,
) -> TrialResult:
    """One task under one strategy. verify: the verifier's view, sources and rule (Engine's verify_view,
    verify_sources and verify_note), the same for every strategy."""
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(store_root or Path(tmp))
        run = new_run(f"{strategy}-{task.id}-r{repeat}", goal=task.question, purpose=PURPOSE, done_when=DONE_WHEN)
        run.state.success_criteria = ["ANSWER:"]
        if task.filed:
            # Parts already done: the run's world covers them, as --exists does for a live run.
            run.world = World(existing_channels=[slug(n) for n in task.filed])
        engine = STRATEGIES[strategy](
            store, adapter=adapter, budget=budget,
            toolbox=Toolbox(roots=[corpus_dir]), max_tool_rounds=tool_rounds, **(verify or {}),
        )
        code = ""
        started = time.perf_counter()
        try:
            engine.run_task(run, context=task_context(task), operator_question="Could a single agent have done this?")
        except InvariantError as e:
            code = e.code
        except Exception:
            code = "CRASH"
        latency = time.perf_counter() - started
    answer = extract_answer(_last_product(run))
    right = grade(answer, task)
    prompt = sum(c.get("prompt_tokens") or 0 for c in run.calls)
    completion = sum(c.get("completion_tokens") or 0 for c in run.calls)
    return TrialResult(
        task_id=task.id, family=task.family, strategy=strategy, repeat=repeat,
        expected=task.answer, answer=answer,
        correct=right and run.status.value == "complete", answer_right=right,
        status=run.status.value, code=code,
        calls=len(run.calls), tokens=prompt + completion,
        prompt_tokens=prompt, completion_tokens=completion,
        tokens_estimated=any(c.get("tokens_estimated") for c in run.calls),
        latency_s=round(latency, 3), workers=run.state.worker_count(),
        proposed=sum(e.event == "gate" for e in run.since_last_plan()),
        refused=sum(e.event == "gate" and not e.detail.get("legal") for e in run.since_last_plan()),
        covered=sum(e.event in ("part_failed", "part_reported") for e in run.log),
        cache_write_tokens=sum(c.get("cache_write_tokens") or 0 for c in run.calls),
        cache_read_tokens=sum(c.get("cache_read_tokens") or 0 for c in run.calls),
        by_model=_by_model(run.calls),
    )


def _by_model(calls: list[dict]) -> dict:
    out: dict = {}
    for c in calls:
        if c.get("model"):
            row = out.setdefault(c["model"], [0, 0, 0, 0])
            for i, key in enumerate(("prompt_tokens", "completion_tokens", "cache_write_tokens", "cache_read_tokens")):
                row[i] += int(c.get(key) or 0)
    return out


def comparison_budget(max_calls: int = 40, context: int = 16_000, max_seconds: float = 600.0) -> Budget:
    """The same cap for every strategy, wide enough that it measures spend rather than truncating it."""
    return Budget(
        max_calls=max_calls, max_tokens=max_calls * context, max_seconds=max_seconds,
        max_tokens_per_call=context, allow_split=True, allow_adapt=True, tier="bench",
    )


def run_comparison(
    suite: Suite,
    adapter_factory: Callable[[], ModelAdapter],
    *,
    strategies: tuple[str, ...] = ("single", "always", "genet"),
    repeats: int = 1,
    budget_factory: Callable[[], Budget] = comparison_budget,
    tool_rounds: int = 3,
    corpus_dir: Path | None = None,
    progress: Callable[[str], None] | None = None,
    stop_when: Callable[[list[TrialResult]], str] | None = None,
    verify: dict | None = None,
) -> list[TrialResult]:
    """Every task under every strategy, interleaved so drift in the endpoint hits all strategies alike.

    A stop_when that returns a reason ends the comparison before the next trial, and so does Ctrl-C.
    Either way the trials already run are returned, so what they spent is kept and reported."""
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        root = suite.write_corpus(corpus_dir or Path(tmp) / "corpus")
        total = len(suite.tasks) * len(strategies) * repeats
        try:
            for r in range(repeats):
                for task in suite.tasks:
                    for strategy in strategies:
                        reason = stop_when(results) if stop_when else ""
                        if reason:
                            if progress:
                                progress(f"stopped after {len(results)} of {total} trials: {reason}")
                            return results
                        res = run_trial(task, strategy, adapter_factory(), root, budget=budget_factory(), tool_rounds=tool_rounds,
                                        repeat=r, verify=verify)
                        results.append(res)
                        if progress:
                            mark = "ok " if res.correct else ("~  " if res.answer_right else "x  ")
                            progress(
                                f"[{len(results)}/{total}] {mark}{strategy:<6} {task.id:<12} "
                                f"{res.calls:>2} calls {res.tokens / 1000:>6.1f}k tok {res.latency_s:>6.1f}s "
                                f"w={res.workers} {res.status}{(' ' + res.code) if res.code else ''}"
                            )
        except KeyboardInterrupt:
            if progress:
                progress(f"interrupted after {len(results)} of {total} trials; the trial in progress is not counted")
    return results


def _priced(prompt: int, completion: int, write: int, read: int, price_in: float, price_out: float) -> float:
    return ((prompt - write - read + CACHE_WRITE * write + CACHE_READ * read) * price_in + completion * price_out) / 1e6


def trial_cost(r: TrialResult, price_in: float, price_out: float, prices: dict | None = None) -> float:
    """What a trial cost: cache writes and reads at their own rates, and with prices (model -> (in, out)) each model's
    tokens at that model's rate; tokens no call attributes to a model at price_in and price_out."""
    write, read = getattr(r, "cache_write_tokens", 0), getattr(r, "cache_read_tokens", 0)
    by = getattr(r, "by_model", None) or {}
    if not prices or not by:
        return _priced(r.prompt_tokens, r.completion_tokens, write, read, price_in, price_out)
    total = sum(_priced(*row, *prices.get(model, (price_in, price_out))) for model, row in by.items())
    rest = [r.prompt_tokens - sum(v[0] for v in by.values()), r.completion_tokens - sum(v[1] for v in by.values()),
            write - sum(v[2] for v in by.values()), read - sum(v[3] for v in by.values())]
    return total + _priced(*rest, price_in, price_out)


def live_spend_cap(spend, max_spend: float, price_in: float, price_out: float) -> Callable[[list[TrialResult]], str]:
    """spend_cap for a replay that goes live part way (tape.Continuing): counts only what went to the model, and stops
    before a trial that could take it past the cap, judged by the costliest trial's live part so far."""
    parts: list[float] = []
    last = [0.0]

    def stop(done: list[TrialResult]) -> str:
        now = spend.cost(price_in, price_out)
        if done:
            parts.append(now - last[0])
            last[0] = now
        if now >= max_spend:
            return f"spend cap: ${now:.4f} sent to the model, of ${max_spend:.2f}"
        if parts and now + max(parts) > max_spend:
            return f"spend cap: ${now:.4f} sent to the model, and the next trial could cost ${max(parts):.4f}, past ${max_spend:.2f}"
        return ""

    return stop


def spend_cap(max_spend: float, price_in: float, price_out: float, prices: dict | None = None) -> Callable[[list[TrialResult]], str]:
    """Stops before a trial that could take spending past the cap, judged by the costliest trial so far."""

    def stop(done: list[TrialResult]) -> str:
        costs = [trial_cost(r, price_in, price_out, prices) for r in done]
        spent = sum(costs)
        if spent >= max_spend:
            return f"spend cap: ${spent:.4f} spent of ${max_spend:.2f}"
        if costs and spent + max(costs) > max_spend:
            return f"spend cap: ${spent:.4f} spent, and the next trial could cost ${max(costs):.4f}, past ${max_spend:.2f}"
        return ""

    return stop


# --- report ---


def _rollup(rows: list[TrialResult], price_in: float | None, price_out: float | None, prices: dict | None = None) -> dict:
    n = len(rows)
    out = {
        "n": n,
        "accuracy": round(sum(r.correct for r in rows) / n, 3),
        "answer_right": round(sum(r.answer_right for r in rows) / n, 3),
        "tokens_mean": round(statistics.mean(r.tokens for r in rows)),
        "calls_mean": round(statistics.mean(r.calls for r in rows), 2),
        "latency_mean_s": round(statistics.mean(r.latency_s for r in rows), 2),
        "split_rate": round(sum(r.workers > 0 for r in rows) / n, 3),
        "abort_rate": round(sum(r.status == "abort" for r in rows) / n, 3),
        "proposed_mean": round(statistics.mean(r.proposed for r in rows), 2),
        "refused_mean": round(statistics.mean(r.refused for r in rows), 2),
        "covered_mean": round(statistics.mean(r.covered for r in rows), 2),
        "tokens_estimated": any(r.tokens_estimated for r in rows),
    }
    if price_in is not None and price_out is not None:
        cost = sum(trial_cost(r, price_in, price_out, prices) for r in rows)
        out["cost_total"] = round(cost, 4)
        out["cost_per_correct"] = round(cost / max(1, sum(r.correct for r in rows)), 4)
    return out


def summarize(results: list[TrialResult], *, price_in: float | None = None, price_out: float | None = None,
              prices: dict | None = None) -> dict:
    strategies = list(dict.fromkeys(r.strategy for r in results))
    families = list(dict.fromkeys(r.family for r in results))
    overall = {s: _rollup([r for r in results if r.strategy == s], price_in, price_out, prices) for s in strategies}
    by_family = {
        f: {s: _rollup([r for r in results if r.strategy == s and r.family == f], price_in, price_out, prices) for s in strategies}
        for f in families
    }
    verdict = {}
    if {"single", "genet"} <= set(overall):
        g = overall["genet"]
        # Only the baselines compete for "best": genet-stated is a variant of genet, and order must not matter.
        best = max((s for s in BASELINES if s in overall), key=lambda s: (overall[s]["accuracy"], -BASELINES.index(s)))
        verdict = {
            "best_baseline": best,
            "genet_accuracy_minus_best_baseline": round(g["accuracy"] - overall[best]["accuracy"], 3),
            "genet_tokens_vs_single": round(g["tokens_mean"] / max(1, overall["single"]["tokens_mean"]), 2),
        }
        if "always" in overall:
            verdict["genet_tokens_vs_always"] = round(g["tokens_mean"] / max(1, overall["always"]["tokens_mean"]), 2)
        if "genet-cards" in overall:
            verdict["cards_tokens_vs_genet"] = round(overall["genet-cards"]["tokens_mean"] / max(1, g["tokens_mean"]), 3)
    return {"overall": overall, "by_family": by_family, "verdict": verdict}


def render(summary: dict) -> str:
    def table(block: dict) -> list[str]:
        has_cost = any("cost_total" in v for v in block.values())
        header = "| strategy | accuracy | tokens/task | calls/task | latency/task | split rate | aborts |" + (" cost |" if has_cost else "")
        rule = "|---|---|---|---|---|---|---|" + ("---|" if has_cost else "")
        lines = [header, rule]
        for s, v in block.items():
            row = (
                f"| {s} | {v['accuracy']:.0%} | {v['tokens_mean']:,} | {v['calls_mean']} | "
                f"{v['latency_mean_s']}s | {v['split_rate']:.0%} | {v['abort_rate']:.0%} |"
            )
            if has_cost:
                row += f" ${v.get('cost_total', 0):.4f} |"
            lines.append(row)
        return lines

    out = ["## Overall", "", *table(summary["overall"]), ""]
    if any(v.get("proposed_mean") for v in summary["overall"].values()):
        out += ["## Plans", "", "| strategy | parts proposed | refused | covered by the lead |", "|---|---|---|---|"]
        out += [f"| {s} | {v.get('proposed_mean', 0)} | {v.get('refused_mean', 0)} | {v.get('covered_mean', 0)} |"
                for s, v in summary["overall"].items()]
        out.append("")
    for family, block in summary["by_family"].items():
        out += [f"## {family}", "", *table(block), ""]
    v = summary.get("verdict") or {}
    if v:
        out += [
            "## Verdict",
            "",
            f"- Best baseline by accuracy: {v['best_baseline']}",
            f"- Genet accuracy minus best baseline: {v['genet_accuracy_minus_best_baseline']:+.0%}",
            f"- Genet tokens vs single: {v['genet_tokens_vs_single']}×",
        ]
        if "genet_tokens_vs_always" in v:
            out.append(f"- Genet tokens vs always-split: {v['genet_tokens_vs_always']}×")
        if "cards_tokens_vs_genet" in v:
            out.append(f"- Genet with cards, tokens vs genet: {v['cards_tokens_vs_genet']}×")
    if any(x.get("tokens_estimated") for x in summary["overall"].values()):
        out += ["", "Token counts are estimated (the adapter reported no usage)."]
    return "\n".join(out) + "\n"


def save(path: Path, *, config: dict, results: list[TrialResult], summary: dict) -> Path:
    path = Path(path)
    atomic.write_text(path, json.dumps({"config": config, "summary": summary, "results": [asdict(r) for r in results]}, indent=2))
    return path


def stderr(line: str) -> None:
    print(line, file=sys.stderr, flush=True)
