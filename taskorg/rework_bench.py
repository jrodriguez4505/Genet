"""Does a lead put right what the verifier failed, once it is told why? The rework bench re-asks the tapes' reworks.

Before v0.11.0 a lead's rework brief said only that the verifier failed the product. So this bench takes each rework
from the tapes, the brief as it was sent after a real failure, and asks again with and without what the verifier said.
Only the lead's call goes to the model, with its tools open on the same files, so the arms compare product by product.

  plain   the brief as it was before v0.11.0
  reason  plus what the verifier said

Measures: of products wrong before the rework, how many come back right, and of products right before it, how many
stay right. A reason that rescues wrong answers must not talk a lead out of right ones.
"""

from __future__ import annotations

import json
import re
import statistics
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from . import atomic
from .adapters import Brief, ModelAdapter
from .compare import comparison_budget, trial_cost
from .errors import InvariantError
from .factory import new_run
from .loop import REWORK_HEAD, Engine, rework_said
from .memory_store import MemoryStore
from .merge_bench import _PRODUCT, _brief, run_jobs
from .suite import Suite, Task, build_suite, extract_answer, grade
from .tools import Toolbox

ARMS = ("plain", "reason")
# On a tape recorded with the reason in the brief, what plain takes out.
_SAID = re.compile(re.escape(REWORK_HEAD) + r"It said: .*?(?=Misses: )", re.S)


@dataclass
class Rework:
    tape: str
    row: int                 # the exchange on the tape, from 1
    task: Task
    suite: Suite
    right_before: bool       # the product the verifier failed, graded
    recorded_after: bool | None  # the reworked product on the tape, graded; None if the tape holds no review of it
    said: str                # what the verifier replied
    cap: int
    tool_rounds: int
    max_calls: int
    brief: Brief


@dataclass
class ReworkResult:
    tape: str
    row: int
    task_id: str
    arm: str
    repeat: int
    right_before: bool
    recorded_after: bool | None
    right_after: bool
    answer: str | None
    code: str
    calls: int
    tokens: int
    prompt_tokens: int
    completion_tokens: int
    tokens_estimated: bool
    latency_s: float


def _reply_claim(reply: str | None) -> str:
    try:
        return str(json.loads(reply or "").get("claim", ""))
    except (ValueError, AttributeError):
        return ""


def reworks_from(path: Path) -> list[Rework]:
    """Every rework on this tape that follows a verifier's reply it can read. A rework's later rounds carry the same
    mode with tool results added, and are the same rework. A trial's calls are together on a tape."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    settings = json.loads(lines[0]).get("compare") or {}
    if not settings:
        return []
    suite = build_suite(seed=settings["seed"], per_family=settings["per_family"], families=tuple(settings["families"]),
                        entities=settings["entities"], distractors=settings["distractors"], filed=settings.get("filed", 0))
    tasks = {t.question: t for t in suite.tasks}
    out: list[Rework] = []
    said, product, goal = "", "", None
    pending: Rework | None = None
    for row, line in enumerate(lines[1:], 1):
        exchange = json.loads(line)
        try:
            sent = json.loads(exchange["request"]["messages"][0]["content"])
        except (KeyError, IndexError, ValueError):
            continue
        if sent.get("function") == "verifier":
            found = _PRODUCT.search(sent.get("packet", ""))
            if pending is not None and sent.get("goal") == pending.task.question and found:
                pending.recorded_after = grade(extract_answer(found.group(1)), pending.task)
            pending = None
            said, product, goal = _reply_claim(exchange.get("reply")), found.group(1) if found else "", sent.get("goal")
        elif sent.get("mode") == "rework" and said and product and sent.get("goal") == goal and goal in tasks and not exchange.get("error"):
            pending = Rework(tape=Path(path).stem, row=row, task=tasks[goal], suite=suite,
                             right_before=grade(extract_answer(product), tasks[goal]), recorded_after=None, said=said,
                             cap=settings["context_tokens"], tool_rounds=settings.get("tool_rounds", 2),
                             max_calls=settings.get("max_calls_per_trial", 40), brief=replace(_brief(sent), view=""))
            out.append(pending)
            said = ""  # the rounds after this one are the same rework
    return out


def in_arm(rework: Rework, arm: str) -> Brief:
    """The brief as this arm sends it. Whatever the tape recorded, plain says nothing of the reason and reason says it once."""
    packet = _SAID.sub(lambda _: REWORK_HEAD, rework.brief.packet, count=1)
    if arm == "reason":
        packet = packet.replace(REWORK_HEAD, REWORK_HEAD + rework_said(rework.said), 1)
    return replace(rework.brief, packet=packet)


def attempt(rework: Rework, arm: str, adapter: ModelAdapter, root: Path, repeat: int = 0) -> ReworkResult:
    """One rework on a fresh run: the lead's call and its tool rounds, under the cap the run had."""
    brief = in_arm(rework, arm)
    code, product = "", ""
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        run = new_run(f"rework-{rework.task.id}-{arm}-r{repeat}", goal=brief.goal, purpose=brief.purpose, done_when=brief.done_when)
        run.state.success_criteria = ["ANSWER:"]
        engine = Engine(MemoryStore(Path(tmp)), adapter=adapter, budget=comparison_budget(rework.max_calls, rework.cap),
                        toolbox=Toolbox(roots=[root]), max_tool_rounds=rework.tool_rounds)
        engine._arm(run)
        lead = run.state.lead_id
        run.switch_skill(lead, lead, brief.skill, "the skill the lead had when this rework was sent")
        try:
            product = engine._act(run, brief, reserve=1).claim
        except InvariantError as e:
            code = e.code
    answer = extract_answer(product)
    prompt = sum(c.get("prompt_tokens") or 0 for c in run.calls)
    completion = sum(c.get("completion_tokens") or 0 for c in run.calls)
    return ReworkResult(tape=rework.tape, row=rework.row, task_id=rework.task.id, arm=arm, repeat=repeat,
                        right_before=rework.right_before, recorded_after=rework.recorded_after, right_after=grade(answer, rework.task),
                        answer=answer, code=code, calls=len(run.calls), tokens=prompt + completion, prompt_tokens=prompt,
                        completion_tokens=completion, tokens_estimated=any(c.get("tokens_estimated") for c in run.calls),
                        latency_s=round(time.perf_counter() - started, 3))


def run_bench(
    reworks: list[Rework],
    adapter_factory: Callable[[], ModelAdapter],
    *,
    arms: tuple[str, ...] = ARMS,
    repeats: int = 1,
    workers: int = 1,
    progress: Callable[[str], None] | None = None,
    stop_when: Callable[[list[ReworkResult]], str] | None = None,
) -> list[ReworkResult]:
    """Every rework under every arm, arms interleaved so endpoint drift hits them alike. See merge_bench.run_jobs."""
    jobs = [(r, rework, arm) for r in range(repeats) for rework in reworks for arm in arms]
    with tempfile.TemporaryDirectory() as tmp:
        roots: dict[str, Path] = {}
        for rework in reworks:
            if rework.tape not in roots:
                roots[rework.tape] = rework.suite.write_corpus(Path(tmp) / rework.tape)

        def work(job, adapter):
            r, rework, arm = job
            return attempt(rework, arm, adapter, roots[rework.tape], r)

        def mark(job, res):
            _, rework, arm = job
            ok = "ok " if res.right_after else "x  "
            return (f"{ok}{arm:<7} {rework.tape[:14]:<14} {rework.task.id:<12} was {'right' if rework.right_before else 'wrong'} "
                    f"{res.calls} calls {res.tokens / 1000:>5.1f}k tok {res.latency_s:>5.1f}s{(' ' + res.code) if res.code else ''}")

        return run_jobs(jobs, work, mark, adapter_factory, workers=workers, progress=progress, stop_when=stop_when, noun="reworks")


def _right(rows: list[ReworkResult]) -> list[int]:
    return [sum(r.right_after for r in rows), len(rows)]


def summarize(results: list[ReworkResult], *, price_in: float | None = None, price_out: float | None = None) -> dict:
    out = {}
    for arm in dict.fromkeys(r.arm for r in results):
        rows = [r for r in results if r.arm == arm]
        block = {
            "n": len(rows),
            "wrong_put_right": _right([r for r in rows if not r.right_before]),
            "right_kept": _right([r for r in rows if r.right_before]),
            "stopped": sum(bool(r.code) for r in rows),
            "tokens_mean": round(statistics.mean(r.tokens for r in rows)),
            "tokens_estimated": any(r.tokens_estimated for r in rows),
        }
        if price_in is not None and price_out is not None:
            block["cost_total"] = round(sum(trial_cost(r, price_in, price_out) for r in rows), 4)
        out[arm] = block
    seen = {(r.tape, r.row): r for r in results}.values()
    recorded = [r for r in seen if not r.right_before and r.recorded_after is not None]
    return {"arms": out, "paired": _paired(results), "recorded": [sum(bool(r.recorded_after) for r in recorded), len(recorded)]}


def _paired(results: list[ReworkResult]) -> dict:
    """The first arm against each other, rework by rework: where the two part is what the reason changes."""
    arms = list(dict.fromkeys(r.arm for r in results))
    first = {(r.tape, r.row, r.repeat): r.right_after for r in results if r.arm == arms[0]} if arms else {}
    out = {}
    for arm in arms[1:]:
        block = {kind: {"first_right_only": 0, "arm_right_only": 0, "both_right": 0, "neither": 0} for kind in ("was_wrong", "was_right")}
        for r in results:
            was = first.get((r.tape, r.row, r.repeat))
            if r.arm != arm or was is None:
                continue
            key = {(True, False): "first_right_only", (False, True): "arm_right_only",
                   (True, True): "both_right", (False, False): "neither"}[(was, r.right_after)]
            block["was_right" if r.right_before else "was_wrong"][key] += 1
        out[arm] = block
    return out


def render(summary: dict) -> str:
    blocks = summary["arms"]
    has_cost = any("cost_total" in v for v in blocks.values())
    lines = ["## Rework bench", "",
             "| arm | wrong before, right after | right before, still right | stopped | tokens/rework |" + (" cost |" if has_cost else ""),
             "|---|---|---|---|---|" + ("---|" if has_cost else "")]
    for arm, v in blocks.items():
        fixed, kept = v["wrong_put_right"], v["right_kept"]
        row = f"| {arm} | {fixed[0]} of {fixed[1]} | {kept[0]} of {kept[1]} | {v['stopped']} | {v['tokens_mean']:,} |"
        if has_cost:
            row += f" ${v.get('cost_total', 0):.4f} |"
        lines.append(row)
    recorded = summary.get("recorded") or [0, 0]
    if recorded[1]:
        lines += ["", f"On the tapes themselves, {recorded[0]} of {recorded[1]} wrong products came back right."]
    first = next(iter(blocks), "")
    for arm, block in (summary.get("paired") or {}).items():
        for kind, n in block.items():
            word = "Wrong" if kind == "was_wrong" else "Right"
            lines += ["", f"{word} before, {first} against {arm}: only {first} right {n['first_right_only']}, only {arm} right "
                          f"{n['arm_right_only']}, both right {n['both_right']}, neither {n['neither']}."]
    if any(v.get("tokens_estimated") for v in blocks.values()):
        lines += ["", "Token counts are estimated (the adapter reported no usage)."]
    return "\n".join(lines) + "\n"


def save(path: Path, *, config: dict, results: list[ReworkResult], summary: dict) -> Path:
    path = Path(path)
    atomic.write_text(path, json.dumps({"config": config, "summary": summary, "results": [asdict(r) for r in results]}, indent=2))
    return path
