"""Does a second plan fit? The plan bench measures the lead's second try on its own.

A plan with a part too big is refused on only some runs: 2 of 6 on one check at 20 companies, none on the next.
So a live run may never show what a lead does when it is told why. The bench hands the run a first plan the
gates refuse, in one of the shapes below, and only the lead's second planning call goes to the model. The gates
then judge that plan as they would in a run, and the bench stops there: what follows a plan they admit is an
ordinary split.

Shapes are the files in each group of the first plan, over the 20 companies a question names:

  8-7-5   the plan a lead wrote on 2 November
  10-10   two groups
  7-7-6   three groups, nearer to fitting

Measures: second plans the gates admit, those that also cover every file the goal names, the largest part, and
tokens a plan.
"""

from __future__ import annotations

import json
import statistics
import string
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import atomic
from .adapters import ModelAdapter
from .budget import Budget
from .compare import DONE_WHEN, PURPOSE, task_context, trial_cost
from .errors import InvariantError
from .factory import new_run
from .gates import Subtask
from .loop import Engine
from .memory_store import MemoryStore
from .suite import Suite, Task, slug
from .tools import Toolbox

ENTITIES = 20
SHAPES: dict[str, tuple[int, ...]] = {"8-7-5": (8, 7, 5), "10-10": (10, 10), "7-7-6": (7, 7, 6)}


def first_plan(task: Task, shape: tuple[int, ...]) -> list[Subtask]:
    """The groups of the plan the gates refuse, the way a lead names them."""
    files = [f"{slug(e)}.md" for e in task.entities]
    if sum(shape) != len(files):
        raise ValueError(f"a plan of {shape} does not cover the {len(files)} files {task.id} names")
    parts, start = [], 0
    for letter, size in zip(string.ascii_lowercase, shape):
        parts.append(Subtask(f"group-{letter}", "figures_get_mixed " + " ".join(files[start:start + size]), skill="retrieve"))
        start += size
    return parts


class _FirstPlanGiven(Engine):
    """An engine whose lead has already planned. Its second plan is the model's."""

    def __init__(self, *args, first: list[Subtask], **kwargs):
        super().__init__(*args, **kwargs)
        self.first = first

    def _propose(self, run, again: str = "") -> list[Subtask]:
        return super()._propose(run, again) if again else list(self.first)


@dataclass
class PlanResult:
    task_id: str
    shape: str
    repeat: int
    asked: bool              # the first plan was refused, so the lead was asked again
    parts: int               # parts the second plan proposed
    admitted: int            # parts the gates admitted
    split: bool              # enough of them to split
    files_wanted: int        # files the goal names
    files_covered: int       # of those, files an admitted part names
    largest: int             # tokens in the largest admitted part
    files_per_part: list[int] = field(default_factory=list)
    refused: str = ""        # the gates' reason, when they refused a part
    code: str = ""
    calls: int = 0
    tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_estimated: bool = False
    latency_s: float = 0.0


def plan_trial(task: Task, shape: str, adapter: ModelAdapter, corpus_dir: Path, *, budget: Budget,
               tool_rounds: int = 4, repeat: int = 0) -> PlanResult:
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(Path(tmp))
        run = new_run(f"plan-{task.id}-{shape}-r{repeat}", goal=task.question, purpose=PURPOSE, done_when=DONE_WHEN)
        engine = _FirstPlanGiven(store, adapter=adapter, budget=budget, toolbox=Toolbox(roots=[corpus_dir]),
                                 max_tool_rounds=tool_rounds, first=first_plan(task, SHAPES[shape]))
        engine._arm(run)
        context = task_context(task)
        run.update_context(run.state.lead_id, context)
        store.remember_working(run.id, "context", context)
        code, verdicts = "", []
        started = time.perf_counter()
        try:
            verdicts = engine._second_plan(run, engine._judge(run, engine._propose(run)), context)
        except InvariantError as e:
            code = e.code
        latency = time.perf_counter() - started
        admitted = [v for v in verdicts if v.legal]
        shares = [engine._material(v.subtask) or {} for v in admitted]
    wanted = {f"{slug(e)}.md" for e in task.entities}
    covered = {Path(p).name for share in shares for p in share} & wanted
    prompt = sum(c.get("prompt_tokens") or 0 for c in run.calls)
    completion = sum(c.get("completion_tokens") or 0 for c in run.calls)
    return PlanResult(
        task_id=task.id, shape=shape, repeat=repeat, asked=any(e.event == "plan_refused" for e in run.log),
        parts=len(verdicts), admitted=len(admitted), split=len(admitted) >= engine.min_split,
        files_wanted=len(wanted), files_covered=len(covered), largest=max((sum(s.values()) for s in shares), default=0),
        files_per_part=[len(s) for s in shares], refused=next((v.refused for v in verdicts if not v.legal), ""),
        code=code, calls=len(run.calls), tokens=prompt + completion, prompt_tokens=prompt, completion_tokens=completion,
        tokens_estimated=any(c.get("tokens_estimated") for c in run.calls), latency_s=round(latency, 3),
    )


def run_bench(
    suite: Suite,
    adapter_factory: Callable[[], ModelAdapter],
    *,
    shapes: tuple[str, ...] = tuple(SHAPES),
    repeats: int = 1,
    budget_factory: Callable[[], Budget],
    tool_rounds: int = 4,
    corpus_dir: Path | None = None,
    progress: Callable[[str], None] | None = None,
    stop_when: Callable[[list[PlanResult]], str] | None = None,
) -> list[PlanResult]:
    """Every question under every shape. A stop_when reason, or Ctrl-C, ends it before the next plan; the plans
    already made are returned."""
    results: list[PlanResult] = []
    total = len(suite.tasks) * len(shapes) * repeats
    with tempfile.TemporaryDirectory() as tmp:
        root = suite.write_corpus(corpus_dir or Path(tmp) / "corpus")
        try:
            for r in range(repeats):
                for task in suite.tasks:
                    for shape in shapes:
                        reason = stop_when(results) if stop_when else ""
                        if reason:
                            if progress:
                                progress(f"stopped after {len(results)} of {total} plans: {reason}")
                            return results
                        res = plan_trial(task, shape, adapter_factory(), root, budget=budget_factory(),
                                         tool_rounds=tool_rounds, repeat=r)
                        results.append(res)
                        if progress:
                            mark = "ok " if res.split and res.files_covered == res.files_wanted else "x  "
                            progress(f"[{len(results)}/{total}] {mark}{shape:<6} {task.id:<12} admitted {res.admitted} of {res.parts}, "
                                     f"files {res.files_per_part}, {res.files_covered} of {res.files_wanted} covered"
                                     f"{(' ' + res.code) if res.code else ''}")
        except KeyboardInterrupt:
            if progress:
                progress(f"interrupted after {len(results)} of {total} plans; the plan in progress is not counted")
    return results


def summarize(results: list[PlanResult], *, price_in: float | None = None, price_out: float | None = None) -> dict:
    out = {}
    for shape in dict.fromkeys(r.shape for r in results):
        rows = [r for r in results if r.shape == shape]
        block = {
            "n": len(rows),
            "asked": sum(r.asked for r in rows),
            "split": sum(r.split for r in rows),
            "whole": sum(r.split and r.files_covered == r.files_wanted for r in rows),
            "still_refused": sum(r.asked and not r.split and not r.code for r in rows),
            "errors": sum(bool(r.code) for r in rows),
            "largest": max(r.largest for r in rows),
            "tokens_mean": round(statistics.mean(r.tokens for r in rows)),
            "tokens_estimated": any(r.tokens_estimated for r in rows),
        }
        if price_in is not None and price_out is not None:
            block["cost_total"] = round(sum(trial_cost(r, price_in, price_out) for r in rows), 4)
        out[shape] = block
    return {"shapes": out}


def render(summary: dict) -> str:
    blocks = summary["shapes"]
    has_cost = any("cost_total" in v for v in blocks.values())
    lines = ["## Plan bench", "",
             "| first plan | plans | asked again | admitted | admitted, every file | refused again | stopped | largest part "
             "| tokens/plan |" + (" cost |" if has_cost else ""),
             "|---|---|---|---|---|---|---|---|---|" + ("---|" if has_cost else "")]
    for shape, v in blocks.items():
        row = (f"| {shape} | {v['n']} | {v['asked']} | {v['split']} | {v['whole']} | {v['still_refused']} | {v['errors']} | "
               f"{v['largest']:,} | {v['tokens_mean']:,} |")
        if has_cost:
            row += f" ${v.get('cost_total', 0):.4f} |"
        lines.append(row)
    if any(v.get("tokens_estimated") for v in blocks.values()):
        lines += ["", "Token counts are estimated (the adapter reported no usage)."]
    return "\n".join(lines) + "\n"


def save(path: Path, *, config: dict, results: list[PlanResult], summary: dict) -> Path:
    path = Path(path)
    atomic.write_text(path, json.dumps({"config": config, "summary": summary, "results": [asdict(r) for r in results]}, indent=2))
    return path
