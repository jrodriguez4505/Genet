"""Side by side: does the gated split beat one agent, or an always-split crew?

Three strategies run the same tasks with the same model, the same tools, the
same budget and tool rounds, the same verify-and-adapt step and the same
concurrency. Only the task organization differs:

  single   one agent works the task; no planning call
  always   crew style: the lead always decomposes and every subtask gets a worker
  genet    the lead proposes sub-agents; the gates judge them (Engine.run_task)

The claim under test: genet matches the better baseline's accuracy at close to
single-agent cost. The report shows where it does and where it does not.
"""

from __future__ import annotations

import functools
import json
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from .adapters import ModelAdapter
from .budget import Budget
from .errors import InvariantError
from .factory import new_run
from .gates import Assessment, Subtask, _could_we
from .loop import Engine
from .memory_store import MemoryStore
from .run import Run
from .models import GATE_ORDER, MAX_WORKERS, SKILLS, GateRecord
from .subtasks import parse_subtasks
from .suite import Suite, Task, extract_answer, grade
from .tools import Toolbox

CONTEXT = (
    "The workspace holds FY2026 operating notes, one markdown file per company, named after it "
    "(for example halvorsen-freight.md for Halvorsen Freight). "
    "Figures are written in prose and the notes contain prior-year figures and look-alike company names. "
    "Use the files; do not guess."
)
PURPOSE = "Answer exactly from the notes. End the product with one line: ANSWER: <value>"
DONE_WHEN = "The product ends with one line 'ANSWER: <value>': a number for amounts, a company name for which-questions."

DECOMPOSE_BRIEF = (
    "PLAN. You lead a crew. Break the work into 2 to 4 subtasks and give each its own worker. "
    "For each, add a request 'subtask:<channel>@<skill>=<what_the_worker_does>' where skill is one of {skills} "
    "(underscores for spaces). A worker that must search or read the workspace needs skill retrieve. "
    "claim: your plan in one or two sentences."
)


class SingleAgent(Engine):
    """Baseline: one agent, no planning call, never splits."""

    def _propose(self, run: Run) -> list[Subtask]:
        return []


class AlwaysSplit(Engine):
    """Baseline: crew style. Always decompose; staff every usable subtask without judging it."""

    min_split = 1

    def _propose(self, run: Run) -> list[Subtask]:
        lead = run.state.lead_id
        run.switch_skill(lead, lead, "reason", "decompose into sub-tasks for the crew")
        plan = self._act(run, self._brief(run, "lead", extra=DECOMPOSE_BRIEF.format(skills="|".join(SKILLS)), mode="plan"))
        run.accept_artifact(plan)
        return parse_subtasks(" ".join(plan.requests))

    def _judge(self, run: Run, subtasks: list[Subtask]) -> list[Assessment]:
        """No gates. Only what the kernel cannot run is dropped: bad ids, repeats, past the worker cap."""
        out, seen = [], set()
        for subtask in subtasks:
            if _could_we(subtask) or subtask.channel_id in seen or len(out) >= MAX_WORKERS:
                continue
            seen.add(subtask.channel_id)
            failure = subtask.named_failure.strip() or "baseline: always split"
            a = Assessment(subtask, GateRecord(False, True, failure, True, subtask.channel_id, GATE_ORDER))
            run._record("gate", a.as_dict() | {"policy": "always-split"})
            out.append(a)
        return out


# genet uses the measured "should we"; genet-stated accepts the lead's reasons, for comparison.
STRATEGIES: dict[str, Callable[..., Engine]] = {
    "single": SingleAgent,
    "always": AlwaysSplit,
    "genet": Engine,
    "genet-stated": functools.partial(Engine, split_policy="stated"),
}


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
) -> TrialResult:
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(store_root or Path(tmp))
        run = new_run(f"{strategy}-{task.id}-r{repeat}", goal=task.question, purpose=PURPOSE, done_when=DONE_WHEN)
        run.state.success_criteria = ["ANSWER:"]
        engine = STRATEGIES[strategy](
            store, adapter=adapter, budget=budget,
            toolbox=Toolbox(roots=[corpus_dir]), max_tool_rounds=tool_rounds,
        )
        code = ""
        started = time.perf_counter()
        try:
            engine.run_task(run, context=CONTEXT, operator_question="Could a single agent have done this?")
        except InvariantError as e:
            code = e.code
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
    )


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
) -> list[TrialResult]:
    """Every task under every strategy, interleaved so drift in the endpoint hits all strategies alike."""
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        root = suite.write_corpus(corpus_dir or Path(tmp) / "corpus")
        total = len(suite.tasks) * len(strategies) * repeats
        for r in range(repeats):
            for task in suite.tasks:
                for strategy in strategies:
                    res = run_trial(task, strategy, adapter_factory(), root, budget=budget_factory(), tool_rounds=tool_rounds, repeat=r)
                    results.append(res)
                    if progress:
                        mark = "ok " if res.correct else ("~  " if res.answer_right else "x  ")
                        progress(
                            f"[{len(results)}/{total}] {mark}{strategy:<6} {task.id:<12} "
                            f"{res.calls:>2} calls {res.tokens / 1000:>6.1f}k tok {res.latency_s:>6.1f}s "
                            f"w={res.workers} {res.status}{(' ' + res.code) if res.code else ''}"
                        )
    return results


# --- report ---


def _rollup(rows: list[TrialResult], price_in: float | None, price_out: float | None) -> dict:
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
        "tokens_estimated": any(r.tokens_estimated for r in rows),
    }
    if price_in is not None and price_out is not None:
        cost = sum(r.prompt_tokens * price_in + r.completion_tokens * price_out for r in rows) / 1e6
        out["cost_total"] = round(cost, 4)
        out["cost_per_correct"] = round(cost / max(1, sum(r.correct for r in rows)), 4)
    return out


def summarize(results: list[TrialResult], *, price_in: float | None = None, price_out: float | None = None) -> dict:
    strategies = list(dict.fromkeys(r.strategy for r in results))
    families = list(dict.fromkeys(r.family for r in results))
    overall = {s: _rollup([r for r in results if r.strategy == s], price_in, price_out) for s in strategies}
    by_family = {
        f: {s: _rollup([r for r in results if r.strategy == s and r.family == f], price_in, price_out) for s in strategies}
        for f in families
    }
    verdict = {}
    if {"single", "genet"} <= set(overall):
        g = overall["genet"]
        best = max((s for s in strategies if s != "genet"), key=lambda s: overall[s]["accuracy"])
        verdict = {
            "best_baseline": best,
            "genet_accuracy_minus_best_baseline": round(g["accuracy"] - overall[best]["accuracy"], 3),
            "genet_tokens_vs_single": round(g["tokens_mean"] / max(1, overall["single"]["tokens_mean"]), 2),
        }
        if "always" in overall:
            verdict["genet_tokens_vs_always"] = round(g["tokens_mean"] / max(1, overall["always"]["tokens_mean"]), 2)
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
    if any(x.get("tokens_estimated") for x in summary["overall"].values()):
        out += ["", "Token counts are estimated (the adapter reported no usage)."]
    return "\n".join(out) + "\n"


def save(path: Path, *, config: dict, results: list[TrialResult], summary: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"config": config, "summary": summary, "results": [asdict(r) for r in results]}, indent=2), encoding="utf-8")
    return path


def stderr(line: str) -> None:
    print(line, file=sys.stderr, flush=True)
