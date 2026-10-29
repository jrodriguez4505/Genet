"""Does the verifier catch a wrong product? The verify bench measures the verifier on its own.

Wrong products are too rare in real runs to count catches: 1 in 12 in the 28 October rerun. So the
harness builds the products, the way a lead's product reads at the end of an aggregate question, and
plants one error in some of them:

  right       every company's figure from its own file
  look-alike  one company's figure from its look-alike's file, which the author read instead of its own
  wrong-year  one company's figure from its own file, but the FY2025 line, not FY2026

The total is always the sum of the figures shown, so the arithmetic never gives an error away. Each
product comes with the record its author would have left: the files it read, and the note it added to
the shared context ("... with look-alike files excluded"). The kernel picks sources from that record
exactly as it does after a real run, and only the verifier's call goes to the model.

Setups, as (view, sources) in checks.py:

  today                shared       none      the verifier as it was: the product and the author's notes
  shared-full          shared       full
  shared-layered       shared       layered
  independent-full     independent  full
  independent-layered  independent  layered

Comparing shared with independent shows what leaving out the author's notes buys; full with layered,
what the cheaper pick misses. Measures: wrong products caught, right products failed, tokens a review.
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
from .loop import Engine
from .memory_store import MemoryStore
from .models import Artifact
from .sim import facts
from .suite import Suite, Task, slug
from .tools import Toolbox

SETUPS: dict[str, tuple[str, str]] = {
    "today": ("shared", "none"),
    "shared-full": ("shared", "full"),
    "shared-layered": ("shared", "layered"),
    "independent-full": ("independent", "full"),
    "independent-layered": ("independent", "layered"),
}
KINDS = ("right", "look-alike", "wrong-year")
# Per question: two right products, one of each wrong kind. Half the products are wrong.
VARIANTS = (("right", 0), ("right", 1), ("look-alike", 0), ("wrong-year", 0))
EVIDENCE = 5  # quotes a product cites, as many as the reply schema allows
UNCERTAINTY = "Several figures rest on search results rather than full file reads, so a misread is possible."


@dataclass
class Built:
    kind: str
    product: Artifact
    read: list[str]          # the files its author read, in order: the record the kernel picks from
    error: dict | None       # company, stated, true, used (file), own (file); None for a right product


@dataclass
class ReviewResult:
    task_id: str
    kind: str
    variant: int
    setup: str
    repeat: int
    verdict: str             # PASS | FAIL | ERROR
    right: bool              # PASS on a right product, FAIL on a wrong one
    error_shown: bool | None  # a wrong product: was the company's own file among the sources shown
    sources_shown: int
    code: str
    calls: int
    tokens: int
    prompt_tokens: int
    completion_tokens: int
    tokens_estimated: bool
    latency_s: float
    reason: str


def _quarter(task: Task) -> str:
    return re.search(r"FY2026 (Q[1-4])", task.question).group(1)


def _line_of(text: str, wanted) -> tuple[int, str] | None:
    """The first sentence for which wanted(sentence) holds, with its line number."""
    for n, line in enumerate(text.splitlines(), 1):
        for sentence in re.split(r"(?<=\.)\s+", line):
            if wanted(sentence):
                return n, sentence.strip()
    return None


def _revenue_line(suite: Suite, name: str, q: str) -> tuple[str, int, str]:
    file = f"{slug(name)}.md"
    value = suite.companies[name].revenue[q]
    found = _line_of(suite.corpus[file], lambda s: abs(facts(s).get(("revenue", q), -1.0) - value) < 1e-9)
    if found is None:
        raise ValueError(f"no FY2026 {q} revenue line in {file}")
    return file, *found


def build(suite: Suite, task: Task, kind: str, variant: int = 0) -> Built | None:
    """One product for an aggregate question, or None when the question has no company to plant this
    kind of error in (a look-alike needs a company whose look-alike is in the corpus)."""
    if task.family != "aggregate":
        raise ValueError(f"the verify bench builds aggregate products, not {task.family}")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    rng = random.Random(f"{suite.seed}:{task.id}:{kind}:{variant}")
    q = _quarter(task)
    names = list(task.entities)
    figures = {n: suite.companies[n].revenue[q] for n in names}
    lines = {n: _revenue_line(suite, n, q) for n in names}
    error = None
    if kind == "look-alike":
        paired = [n for n in names if suite.companies[n].sister]
        apart = [n for n in paired if suite.companies[n].sister not in names]
        if not paired:
            return None
        n = rng.choice(apart or paired)
        sister = suite.companies[n].sister
        file, line, sentence = _revenue_line(suite, sister, q)
        figures[n], lines[n] = suite.companies[sister].revenue[q], (file, line, sentence)
        error = {"company": n, "stated": figures[n], "true": suite.companies[n].revenue[q], "used": file, "own": f"{slug(n)}.md"}
    elif kind == "wrong-year":
        n = rng.choice(names)
        old = suite.companies[n].revenue_fy2025_q3
        own = f"{slug(n)}.md"
        found = _line_of(suite.corpus[own], lambda s: s.startswith("In FY2025, third-quarter revenue had been"))
        figures[n], lines[n] = old, (own, *found)
        error = {"company": n, "stated": old, "true": suite.companies[n].revenue[q], "used": own, "own": own}
    total = round(sum(figures.values()), 1)
    claim = (f"Sum of FY2026 {q} revenue for the {len(names)} named companies, from each company's own file: "
             + "; ".join(f"{n} {figures[n]:.1f}" for n in names) + f". Total = {total:.1f} $M. ANSWER: {total:.1f}")
    cited = rng.sample(names, min(EVIDENCE, len(names)))
    evidence = [f'{lines[n][0]}:{lines[n][1]}: "{lines[n][2]}"' for n in cited]
    note = (f"FY2026 {q} revenue for {len(names)} named companies was collected from their notes and summed to "
            f"{total:.1f} $M, with look-alike files excluded.")
    product = Artifact(claim=claim, evidence=evidence, uncertainty=UNCERTAINTY, channel_id="lead-merge", context_update=note)
    return Built(kind=kind, product=product, read=list(dict.fromkeys(lines[n][0] for n in names)), error=error)


def products(suite: Suite) -> list[tuple[Task, int, Built]]:
    """Every product the bench reviews: VARIANTS for each aggregate question, in task order."""
    out = []
    for task in suite.tasks:
        if task.family != "aggregate":
            continue
        for kind, variant in VARIANTS:
            built = build(suite, task, kind, variant)
            if built is not None:
                out.append((task, variant, built))
    return out


def review_trial(
    task: Task,
    built: Built,
    setup: str,
    adapter: ModelAdapter,
    corpus_dir: Path,
    *,
    budget: Budget,
    variant: int = 0,
    repeat: int = 0,
) -> ReviewResult:
    """One review: the author's record and product on a fresh run, then the verifier's call alone."""
    view, sources = SETUPS[setup]
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(Path(tmp))
        run = new_run(f"verify-{task.id}-{built.kind}-{variant}-r{repeat}", goal=task.question, purpose=PURPOSE,
                      done_when=DONE_WHEN)
        run.state.success_criteria = ["ANSWER:"]
        engine = Engine(store, adapter=adapter, budget=budget, toolbox=Toolbox(roots=[corpus_dir]),
                        verify_view=view, verify_sources=sources)
        engine._arm(run)
        lead = run.state.lead_id
        context = task_context(task)
        run.update_context(lead, context)
        store.remember_working(run.id, "context", context)
        for file in built.read:
            # What the author's own reads would have put on the record.
            run._record("tool", {"slot": lead, "channel": "", "request": f"read:{file}", "chars": 0, "read": [file]})
        run.accept_artifact(built.product)  # its note joins the shared context, as an author's does
        store.remember_working(run.id, "product", built.product.claim)
        code = ""
        started = time.perf_counter()
        try:
            _, verified = engine._verify(run, built.product, adapt=False)
        except InvariantError as e:
            verified, code = False, e.code
        latency = time.perf_counter() - started
    checks_made = [a for a in run.artifacts if a.channel_id == "verify"]
    said = checks_made[-1].claim if checks_made else ""
    if verified:
        verdict = "PASS"
    elif said.lstrip().upper().startswith("FAIL") or (code == "VERIFY" and checks_made):
        verdict = "FAIL"
    else:
        verdict = "ERROR"
    picked = [e.detail for e in run.log if e.event == "verify_sources"]
    shown = picked[-1]["shown"] if picked else 0
    error_shown = None
    if built.error is not None:
        files = [p["file"] for p in (picked[-1]["picked"] if picked else [])][:shown]
        error_shown = built.error["own"] in files
    prompt = sum(c.get("prompt_tokens") or 0 for c in run.calls)
    completion = sum(c.get("completion_tokens") or 0 for c in run.calls)
    wrong = built.error is not None
    return ReviewResult(
        task_id=task.id, kind=built.kind, variant=variant, setup=setup, repeat=repeat, verdict=verdict,
        right=(verdict == "FAIL") if wrong else (verdict == "PASS"), error_shown=error_shown, sources_shown=shown,
        code=code, calls=len(run.calls), tokens=prompt + completion, prompt_tokens=prompt, completion_tokens=completion,
        tokens_estimated=any(c.get("tokens_estimated") for c in run.calls), latency_s=round(latency, 3),
        reason=said[:240],
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
    stop_when: Callable[[list[ReviewResult]], str] | None = None,
) -> list[ReviewResult]:
    """Every product under every setup, setups interleaved so endpoint drift hits them alike. A stop_when
    reason, or Ctrl-C, ends it before the next review; the reviews already made are returned."""
    results: list[ReviewResult] = []
    items = products(suite)
    total = len(items) * len(setups) * repeats
    with tempfile.TemporaryDirectory() as tmp:
        root = suite.write_corpus(corpus_dir or Path(tmp) / "corpus")
        try:
            for r in range(repeats):
                for task, variant, built in items:
                    for setup in setups:
                        reason = stop_when(results) if stop_when else ""
                        if reason:
                            if progress:
                                progress(f"stopped after {len(results)} of {total} reviews: {reason}")
                            return results
                        res = review_trial(task, built, setup, adapter_factory(), root, budget=budget_factory(),
                                           variant=variant, repeat=r)
                        results.append(res)
                        if progress:
                            mark = "ok " if res.right else "x  "
                            progress(f"[{len(results)}/{total}] {mark}{setup:<19} {task.id:<12} {built.kind:<10} "
                                     f"{res.verdict:<5} {res.sources_shown:>2} src {res.tokens / 1000:>5.1f}k tok "
                                     f"{res.latency_s:>5.1f}s{(' ' + res.code) if res.code and res.code != 'VERIFY' else ''}")
        except KeyboardInterrupt:
            if progress:
                progress(f"interrupted after {len(results)} of {total} reviews; the review in progress is not counted")
    return results


def _rate(hits: int, n: int) -> float | None:
    return round(hits / n, 3) if n else None


def summarize(results: list[ReviewResult], *, price_in: float | None = None, price_out: float | None = None) -> dict:
    out = {}
    for setup in dict.fromkeys(r.setup for r in results):
        rows = [r for r in results if r.setup == setup]
        wrong = [r for r in rows if r.kind != "right"]
        right = [r for r in rows if r.kind == "right"]
        block = {
            "n": len(rows),
            "caught": _rate(sum(r.verdict == "FAIL" for r in wrong), len(wrong)),
            "false_fail": _rate(sum(r.verdict == "FAIL" for r in right), len(right)),
            "errors": sum(r.verdict == "ERROR" for r in rows),
            "by_kind": {k: _rate(sum(r.verdict == "FAIL" for r in wrong if r.kind == k), sum(r.kind == k for r in wrong))
                        for k in KINDS[1:] if any(r.kind == k for r in wrong)},
            # Of the wrong products, how many had the company's own file among the sources shown.
            "error_shown": _rate(sum(bool(r.error_shown) for r in wrong), len(wrong)),
            "sources_mean": round(statistics.mean(r.sources_shown for r in rows), 2),
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
    lines = ["## Verify bench", "",
             "| setup | wrong caught | look-alike | wrong-year | right failed | error file shown | sources | tokens/review |"
             + (" cost |" if has_cost else ""),
             "|---|---|---|---|---|---|---|---|" + ("---|" if has_cost else "")]
    for setup, v in blocks.items():
        kinds = v["by_kind"]
        row = (f"| {setup} | {_pct(v['caught'])} | {_pct(kinds.get('look-alike'))} | {_pct(kinds.get('wrong-year'))} | "
               f"{_pct(v['false_fail'])} | {_pct(v['error_shown'])} | {v['sources_mean']} | {v['tokens_mean']:,} |")
        if has_cost:
            row += f" ${v.get('cost_total', 0):.4f} |"
        lines.append(row)
    if any(v["errors"] for v in blocks.values()):
        lines += ["", "Reviews that ended in an error, not a verdict: "
                  + ", ".join(f"{s} {v['errors']}" for s, v in blocks.items() if v["errors"])]
    if any(v.get("tokens_estimated") for v in blocks.values()):
        lines += ["", "Token counts are estimated (the adapter reported no usage)."]
    return "\n".join(lines) + "\n"


def save(path: Path, *, config: dict, results: list[ReviewResult], summary: dict) -> Path:
    path = Path(path)
    atomic.write_text(path, json.dumps({"config": config, "summary": summary, "results": [asdict(r) for r in results]}, indent=2))
    return path
