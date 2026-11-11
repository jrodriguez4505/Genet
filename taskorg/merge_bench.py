"""Does the verifier fail a real merge, and what would stop it? The merge bench reviews the merges on the tapes.

The verify bench builds its products, and a clean one passes: its verifier failed none of 12 right products shaped
like a merge. The runs' own merges fail far more often. So this bench takes the verifier's requests from the tapes,
the product and sources as they were sent after a real split, and asks again under each rule. Only the verifier's
call goes to the model, and the same brief goes under each rule, so the rules compare product by product.

  none    the source rule alone, the default before v0.10.0
  told    plus: the files are a sample, and a figure no file covers is no reason to FAIL
  headed  plus: a line that gives no year takes the year in its file's heading
  both    plus both
  named   both, and: a product that leaves out, sets aside or counts as zero anything the goal names has not answered it

Measures: right answers failed, split by what the verifier said when recorded, and wrong answers caught. A rule that
fails fewer right answers must still catch errors, which these few wrong merges cannot show: the verify bench's split
arm measures that.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from . import atomic, checks
from .adapters import Brief, ModelAdapter
from .compare import trial_cost
from .errors import InvariantError
from .live import message_text
from .loop import REVIEW_END
from .suite import build_suite, extract_answer, grade

RULES: dict[str, str] = {
    "none": "",
    "told": checks.SAMPLE_RULE,
    "headed": checks.HEADING_RULE,
    "both": checks.SAMPLE_RULE + checks.HEADING_RULE,
    "named": checks.SAMPLE_RULE + checks.NAMED_RULE + checks.HEADING_RULE,
    "aside": checks.SAMPLE_RULE + checks.ASIDE_RULE + checks.HEADING_RULE,
    "same": checks.SAMPLE_RULE + checks.SAME_VERIFY + checks.HEADING_RULE,
}
_PRODUCT = re.compile(r"PRODUCT UNDER REVIEW[^\n]*\n(.*?)(?:\n" + re.escape(REVIEW_END) + r"|\nEVIDENCE GIVEN WITH IT\n|\n"
                      + re.escape(checks.SOURCES_HEAD) + ")", re.S)
_BODY = re.compile(r"PRODUCT UNDER REVIEW[^\n]*\n(.*?)\n" + re.escape(checks.SOURCES_HEAD), re.S)
# A product that voices a doubt of its own. A rough match: it sorts products for reading, and decides nothing.
_DOUBT = re.compile(r"provisional|unconfirm|not confirmed|no year|year[- ]un|unlabel|without a year|not labell?ed|could not|"
                    r"cannot|can't|not verified|unverified|assum|ambiguous|partial|incomplete|not found|missing|not reported|"
                    r"may be|might|caveat|tentative", re.I)


@dataclass
class Merge:
    tape: str
    row: int                 # the exchange on the tape, from 1
    task_id: str
    right: bool              # the product's answer, graded
    doubt: bool              # the product voices a doubt of its own
    recorded: str            # what the verifier said on the tape: PASS | FAIL | OTHER
    cap: int                 # the per-call cap the run had
    brief: Brief


@dataclass
class MergeResult:
    tape: str
    row: int
    task_id: str
    rule: str
    repeat: int
    right: bool
    doubt: bool
    recorded: str
    verdict: str             # PASS | FAIL | OTHER | ERROR
    code: str
    tokens: int
    prompt_tokens: int
    completion_tokens: int
    tokens_estimated: bool
    latency_s: float
    reason: str


def _verdict(claim: str) -> str:
    word = (claim or "").lstrip().upper()
    return "PASS" if word.startswith("PASS") else "FAIL" if word.startswith("FAIL") else "OTHER"


def _recorded(reply: str | None) -> str:
    try:
        return _verdict(json.loads(reply or "").get("claim", ""))
    except (ValueError, AttributeError):
        return "OTHER"


def _brief(sent: dict) -> Brief:
    return Brief(slot_function=sent["function"], skill=sent["skill"], packet=sent["packet"], goal=sent["goal"],
                 purpose=sent["purpose"], context=sent["context"], done_when=sent["done_when"],
                 channel_id=sent.get("channel_id") or "", isolated=sent.get("isolated", True), tools=sent.get("tools"),
                 success_criteria=sent.get("success_criteria"), mode=sent.get("mode", ""), view="independent")


def merges_from(path: Path) -> list[Merge]:
    """Every review of a product after a split on this tape, under the independent view with sources open. A trial's
    calls are together on a tape, so a verifier's call follows its own sub-agents' since the lead last planned."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    head = json.loads(lines[0])
    settings = head.get("compare") or {}
    if not settings or settings.get("verify_view") != "independent":
        return []
    suite = build_suite(seed=settings["seed"], per_family=settings["per_family"], families=tuple(settings["families"]),
                        entities=settings["entities"], distractors=settings["distractors"], filed=settings.get("filed", 0))
    tasks = {t.question: t for t in suite.tasks}
    out: list[Merge] = []
    workers, goal = 0, None
    for row, line in enumerate(lines[1:], 1):
        exchange = json.loads(line)
        try:
            sent = json.loads(message_text(exchange["request"]["messages"][0]["content"]))
        except (KeyError, IndexError, ValueError):
            continue
        fn, mode = sent.get("function"), sent.get("mode")
        if sent.get("goal") != goal or (fn == "lead" and mode in ("plan", "work")):
            workers, goal = 0, sent.get("goal")
        if fn == "worker":
            workers += 1
        if fn != "verifier" or not workers or exchange.get("error") or goal not in tasks:
            continue
        packet = sent.get("packet", "")
        product = _PRODUCT.search(packet)
        if checks.SOURCE_RULE not in packet or not product:
            continue
        body = _BODY.search(packet)
        out.append(Merge(tape=Path(path).stem, row=row, task_id=tasks[goal].id,
                         right=grade(extract_answer(product.group(1)), tasks[goal]),
                         doubt=bool(_DOUBT.search(body.group(1) if body else product.group(1))),
                         recorded=_recorded(exchange.get("reply")), cap=settings["context_tokens"], brief=_brief(sent)))
    return out


def with_rule(brief: Brief, rule: str) -> Brief:
    """The same brief, with the rule's words after the source rule in place of any it was recorded with, so none
    means none on a tape recorded under another. Longest first, or both would lose only one of its sentences."""
    for recorded in sorted(RULES.values(), key=len, reverse=True):
        said = checks.SOURCE_RULE + recorded
        if said in brief.packet:
            return replace(brief, packet=brief.packet.replace(said, checks.SOURCE_RULE + RULES[rule], 1))
    return brief


def review(merge: Merge, rule: str, adapter: ModelAdapter, repeat: int = 0) -> MergeResult:
    brief = with_rule(merge.brief, rule)
    brief = replace(brief, max_reply_tokens=max(1, merge.cap - adapter.estimate_tokens(brief)))
    code, said, verdict = "", "", "ERROR"
    started = time.perf_counter()
    try:
        said = adapter.act(brief).claim
        verdict = _verdict(said)
    except InvariantError as e:
        code = e.code
    latency = time.perf_counter() - started
    usage = getattr(adapter, "last_usage", None) or {}
    prompt, completion = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    return MergeResult(tape=merge.tape, row=merge.row, task_id=merge.task_id, rule=rule, repeat=repeat, right=merge.right,
                       doubt=merge.doubt, recorded=merge.recorded, verdict=verdict, code=code, tokens=prompt + completion,
                       prompt_tokens=prompt, completion_tokens=completion, tokens_estimated=bool(usage.get("estimated")) or not usage,
                       latency_s=round(latency, 3), reason=said[:240])


def run_bench(
    merges: list[Merge],
    adapter_factory: Callable[[], ModelAdapter],
    *,
    rules: tuple[str, ...] = tuple(RULES),
    repeats: int = 1,
    workers: int = 1,
    progress: Callable[[str], None] | None = None,
    stop_when: Callable[[list[MergeResult]], str] | None = None,
) -> list[MergeResult]:
    """Every merge under every rule, rules interleaved so endpoint drift hits them alike. See run_jobs."""
    jobs = [(r, merge, rule) for r in range(repeats) for merge in merges for rule in rules]

    def work(job, adapter):
        r, merge, rule = job
        return review(merge, rule, adapter, r)

    def mark(job, res):
        _, merge, rule = job
        ok = "ok " if res.verdict == ("PASS" if res.right else "FAIL") else "x  "
        return (f"{ok}{rule:<7} {merge.tape[:8]:<8} {merge.task_id:<12} {'right' if merge.right else 'wrong'} {res.verdict:<5} "
                f"was {merge.recorded:<5} {res.tokens / 1000:>5.1f}k tok {res.latency_s:>5.1f}s")

    return run_jobs(jobs, work, mark, adapter_factory, workers=workers, progress=progress, stop_when=stop_when, noun="reviews")


def run_jobs(jobs: list, work: Callable, mark: Callable, adapter_factory: Callable[[], ModelAdapter], *, workers: int = 1,
             progress: Callable[[str], None] | None = None, stop_when: Callable[[list], str] | None = None, noun: str = "reviews") -> list:
    """Each job with its own adapter, in the order listed whatever order they finish in. A stop_when reason, or Ctrl-C,
    ends it before the next job; the results already made are returned. Jobs under way count against stop_when at the
    largest so far, so a spend cap holds with workers too."""
    done: dict = {}
    running: dict = {}

    def collect(finished) -> None:
        for future in finished:
            i = running.pop(future)
            res = done[i] = future.result()
            if progress:
                progress(f"[{len(done)}/{len(jobs)}] {mark(jobs[i], res)}")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        try:
            for i, job in enumerate(jobs):
                while len(running) >= max(1, workers):
                    collect(wait(running, return_when=FIRST_COMPLETED).done)
                so_far = list(done.values())
                worst = max(so_far, key=lambda x: x.tokens, default=None)
                reason = stop_when(so_far + ([worst] * len(running) if worst else [])) if stop_when else ""
                if reason:
                    if progress:
                        progress(f"stopped after {len(done)} of {len(jobs)} {noun}: {reason}")
                    break
                running[pool.submit(work, job, adapter_factory())] = i
            while running:
                collect(wait(running, return_when=FIRST_COMPLETED).done)
        except KeyboardInterrupt:
            for future in running:
                future.cancel()
            if progress:
                progress(f"interrupted after {len(done)} of {len(jobs)} {noun}; those in progress are not counted")
    return [done[i] for i in sorted(done)]


def _failed(rows: list[MergeResult]) -> list[int]:
    return [sum(r.verdict == "FAIL" for r in rows), len(rows)]


def summarize(results: list[MergeResult], *, price_in: float | None = None, price_out: float | None = None) -> dict:
    out = {}
    for rule in dict.fromkeys(r.rule for r in results):
        rows = [r for r in results if r.rule == rule]
        right = [r for r in rows if r.right]
        block = {
            "n": len(rows),
            "right_failed": _failed(right),
            # Failed before, and failed again: what the rule did not stop. Passed before, and failed now: what it broke.
            "was_fail": _failed([r for r in right if r.recorded == "FAIL"]),
            "was_pass": _failed([r for r in right if r.recorded == "PASS"]),
            "doubt": _failed([r for r in right if r.doubt]),
            "no_doubt": _failed([r for r in right if not r.doubt]),
            "wrong_caught": _failed([r for r in rows if not r.right]),
            "errors": sum(r.verdict in ("ERROR", "OTHER") for r in rows),
            "tokens_mean": round(statistics.mean(r.tokens for r in rows)),
            "tokens_estimated": any(r.tokens_estimated for r in rows),
        }
        if price_in is not None and price_out is not None:
            block["cost_total"] = round(sum(trial_cost(r, price_in, price_out) for r in rows), 4)
        out[rule] = block
    return {"rules": out, "paired": _paired(results)}


def _paired(results: list[MergeResult]) -> dict:
    """The first rule against each other, product by product. Where two rules part is what a rule changes, and a
    product with no verdict under either says nothing about it, so it is left out."""
    rules = list(dict.fromkeys(r.rule for r in results))
    first = {(r.tape, r.row, r.repeat): r.verdict for r in results if r.rule == rules[0]} if rules else {}
    out = {}
    for rule in rules[1:]:
        block = {kind: {"first_failed_only": 0, "rule_failed_only": 0, "both_failed": 0, "both_passed": 0} for kind in ("right", "wrong")}
        for r in results:
            was = first.get((r.tape, r.row, r.repeat))
            if r.rule != rule or was not in ("PASS", "FAIL") or r.verdict not in ("PASS", "FAIL"):
                continue
            key = {("FAIL", "PASS"): "first_failed_only", ("PASS", "FAIL"): "rule_failed_only",
                   ("FAIL", "FAIL"): "both_failed", ("PASS", "PASS"): "both_passed"}[(was, r.verdict)]
            block["right" if r.right else "wrong"][key] += 1
        out[rule] = block
    return out


def _of(pair: list[int]) -> str:
    return f"{pair[0]} of {pair[1]}"


def render(summary: dict) -> str:
    blocks = summary["rules"]
    has_cost = any("cost_total" in v for v in blocks.values())
    lines = ["## Merge bench", "",
             "| rule | right answers failed | failed when recorded, failed again | passed when recorded, failed now "
             "| with a doubt of its own | without | wrong answers caught | no verdict | tokens/review |" + (" cost |" if has_cost else ""),
             "|---|---|---|---|---|---|---|---|---|" + ("---|" if has_cost else "")]
    for rule, v in blocks.items():
        row = (f"| {rule} | {_of(v['right_failed'])} | {_of(v['was_fail'])} | {_of(v['was_pass'])} | {_of(v['doubt'])} | "
               f"{_of(v['no_doubt'])} | {_of(v['wrong_caught'])} | {v['errors']} | {v['tokens_mean']:,} |")
        if has_cost:
            row += f" ${v.get('cost_total', 0):.4f} |"
        lines.append(row)
    first = next(iter(blocks), "")
    for rule, block in (summary.get("paired") or {}).items():
        for kind, n in block.items():
            lines += ["", f"{kind.capitalize()} answers, {first} against {rule}: {first} alone failed {n['first_failed_only']}, "
                          f"{rule} alone failed {n['rule_failed_only']}, both failed {n['both_failed']}, both passed {n['both_passed']}."]
    if any(v.get("tokens_estimated") for v in blocks.values()):
        lines += ["", "Token counts are estimated (the adapter reported no usage)."]
    return "\n".join(lines) + "\n"


def save(path: Path, *, config: dict, results: list[MergeResult], summary: dict) -> Path:
    path = Path(path)
    atomic.write_text(path, json.dumps({"config": config, "summary": summary, "results": [asdict(r) for r in results]}, indent=2))
    return path
