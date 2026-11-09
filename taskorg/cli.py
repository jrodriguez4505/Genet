from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .budget import Budget
from .checks import AUTHOR_RULES, SOURCES, VIEWS
from .errors import InvariantError
from .factory import new_run
from .gates import Subtask, World
from .live import pick_adapter
from .loop import Engine
from .memory_store import MemoryStore
from .persist import load_run, save_run
from .reads import attach_reads
from .situation import DEFAULT_ABORT, parse_abort
from .subtasks import parse_subtasks
from .tools import Toolbox
from .report_bench import SETUPS as REPORT_SETUPS
from .merge_bench import RULES as MERGE_RULES
from .plan_bench import SHAPES as PLAN_SHAPES
from .verify_bench import ARMS as VERIFY_ARMS, DEFAULT_SETUPS as VERIFY_DEFAULT_SETUPS, SETUPS as VERIFY_SETUPS


DEFAULT_GUIDELINES = """# Genet guidelines (v1)

- Structure lives in code. Prompts describe work, not authority.
- Only the lead may change the roster.
- Context decides which skill is active. The goal stays fixed until revised.
- Inspect context → activate a skill → gates → maybe add a worker.
- The reviewer is heard and answered. The reviewer does not take over the roster.
- Could-we is the last gate, not the first.
"""


def _store(root) -> MemoryStore:
    """Plain file store. Guidelines are seeded once; an operator's edits are kept."""
    store = MemoryStore(Path(root))
    if not store.read_guidelines("standing"):
        store.write_guidelines("standing", DEFAULT_GUIDELINES)
    return store


def _whole(least: int):
    """An argparse type: a whole number, at least `least`."""
    def parse(text: str) -> int:
        value = int(text)
        if value < least:
            raise argparse.ArgumentTypeError(f"must be at least {least}, got {value}")
        return value
    return parse


def _finite(least: float, *, strict: bool):
    """An argparse type: a finite number above (strict) or at least `least`. nan would switch a cap off."""
    def parse(text: str) -> float:
        value = float(text)
        if not math.isfinite(value) or value < least or (strict and value == least):
            raise argparse.ArgumentTypeError(f"must be a finite number {'above' if strict else 'at least'} {least}, got {text}")
        return value
    return parse


def _add_budget_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tier", default="tight", choices=["tight", "normal", "open"],
                   help="budget tier: tight = single agent; normal = may replan; open = may fan out")
    p.add_argument("--max-calls", type=_whole(1), default=None)
    p.add_argument("--max-tokens", type=_whole(1), default=None)
    p.add_argument("--max-seconds", type=_finite(0, strict=True), default=None)
    p.add_argument("--max-tokens-per-call", type=_whole(1), default=None)


def _add_run_args(p: argparse.ArgumentParser, *, required: tuple[str, ...] = (), **defaults: str) -> None:
    """Flags every run command shares. defaults maps flag name (underscored) to default."""
    for flag in ("id", "goal", "purpose", "done_when", "context"):
        name = "--" + flag.replace("_", "-")
        if flag in required:
            p.add_argument(name, required=True)
        else:
            p.add_argument(name, default=defaults[flag])
    p.add_argument("--store", default="data")
    p.add_argument("--out", default=None, help="saved run (default data/runs/<id>.json)")
    p.add_argument("--adapter", default="stub", choices=["stub", "live", "anthropic"])
    p.add_argument("--read", action="append", default=[], help="file text into working memory; not a new sub-agent")
    p.add_argument("--criteria", action="append", default=[], help="success criterion the product must show")
    p.add_argument("--exists", action="append", default=[], help="file already on disk; its name covers a channel")
    p.add_argument("--workspace", action="append", default=[], help="directory specialists may read and search")
    p.add_argument("--isolate", action="store_true",
                   help="the sub-tasks must not share a context (a declared reason to fan out)")
    p.add_argument("--no-lessons", action="store_true",
                   help="do not write lessons from a failed run to the shared guidelines")
    p.add_argument("--split-policy", default="measured", choices=["measured", "stated"],
                   help="measured: fan out only for declared isolation or material that does not fit one context; "
                        "stated: the lead's named reasons are enough")
    p.add_argument("--verify-view", default="independent", choices=list(VIEWS),
                   help="what the verifier sees: shared (every note), independent (not the author's notes)")
    p.add_argument("--verify-sources", default="layered", choices=list(SOURCES),
                   help="workspace files the kernel opens for the verifier: layered (default), full, or none "
                        "(the brief before v0.7.0, which older tapes replay)")
    p.add_argument("--verify-rule", default="both", choices=list(MERGE_RULES),
                   help="words after the verifier's source rule, with sources open: both (the default), told, headed, named, aside, "
                        "or none (the brief before v0.10.0, which older tapes replay). merge-bench says what each is")
    p.add_argument("--no-rework-reason", dest="rework_reason", action="store_false",
                   help="leave out of the lead's rework brief why the verifier failed its product (as older tapes hold it)")
    p.add_argument("--author-rule", default="none", choices=list(AUTHOR_RULES),
                   help="words for the lead's and sub-agents' briefs: none (the default), or headed, a line that gives no "
                        "year takes the year in its file's heading")
    p.add_argument("--gap-check", action="store_true",
                   help="send back, once, a product the verifier passed that says itself it has no figure for something, adds 0 "
                        "for it or set it aside; a reworked product that still says so stops the run. Off by default")
    p.add_argument("--abort", action="append", default=[], metavar="CRITERION",
                   help="stop at a decision point when this is met: forecast_short (the budget cannot finish the "
                        f"work; the default), parts_failed:N (N parts' sub-agents failed), or none. "
                        f"Naming one replaces the default {list(DEFAULT_ABORT)}")
    p.add_argument("--main-effort", default="", metavar="CHANNEL",
                   help="the part the goal depends on most; the gates judge it first")
    p.add_argument("--report-up", action="store_true",
                   help="a sub-agent may hand its part back with replan:REASON when the plan is wrong for it")
    p.add_argument("--cards", action="store_true",
                   help="show the lead a card for each position it can staff, with its record from past runs")
    _add_budget_args(p)


def _budget(args: argparse.Namespace) -> Budget:
    b = Budget.for_tier(getattr(args, "tier", "tight"))
    if args.max_calls is not None:
        b.max_calls = args.max_calls
    if args.max_tokens is not None:
        b.max_tokens = args.max_tokens
    if args.max_seconds is not None:
        b.max_seconds = args.max_seconds
    if args.max_tokens_per_call is not None:
        b.max_tokens_per_call = args.max_tokens_per_call
    return b


def _new_run(args: argparse.Namespace, store: MemoryStore):
    """Fresh run: clean working memory, then operator reads, criteria, and world."""
    run = new_run(args.id, args.goal, args.purpose, args.done_when)
    store.reset_working(run.id)
    attach_reads(store, run, args.read)
    if args.criteria:
        criteria = [c for c in args.criteria if c.strip()]
        if not criteria:
            raise InvariantError("CLI", "--criteria is blank; name what the product must show")
        run.state.success_criteria = criteria
    if args.abort:
        # Naming a criterion replaces the default; `none` alone turns every criterion off.
        run.state.abort_criteria = parse_abort(a for a in args.abort if a.strip().lower() != "none")
    run.state.primary = args.main_effort.strip()
    exists = [str(p) for p in args.exists]
    run.world = World(existing_files=exists, existing_channels=[Path(p).stem for p in exists])
    return run


def _engine(args: argparse.Namespace, store: MemoryStore) -> Engine:
    for root in args.workspace:
        if not Path(root).is_dir():
            raise InvariantError("READ", f"workspace is not a directory: {root}")
    toolbox = Toolbox(roots=args.workspace, files=args.read)
    return Engine(store, adapter=pick_adapter(args.adapter), budget=_budget(args), toolbox=toolbox,
                  split_policy=args.split_policy, isolation_required=args.isolate, lessons=not args.no_lessons,
                  verify_view=args.verify_view, verify_sources=args.verify_sources, verify_note=MERGE_RULES[args.verify_rule],
                  rework_reason=args.rework_reason, author_note=AUTHOR_RULES[args.author_rule],
                  report_up=args.report_up,
                  cards=args.cards, gap_check=args.gap_check)


def _out_path(raw: str | None, default: Path) -> Path:
    """Where results go, checked before any work starts, so a bad path cannot waste a run."""
    out = Path(raw) if raw else default
    if out.is_dir():
        raise InvariantError("CLI", f"--out is a directory, not a file: {out}")
    if out.parent.exists() and not out.parent.is_dir():
        raise InvariantError("CLI", f"--out is inside something that is not a directory: {out.parent}")
    return out


def _start(args: argparse.Namespace):
    """Everything that can fail before the run starts: the out path, the store, the run, the engine.
    An error here writes nothing, so it can never overwrite the last saved run."""
    out = _out_path(args.out, Path("data/runs") / f"{args.id}.json")
    store = _store(args.store)
    run = _new_run(args, store)
    return store, run, _engine(args, store), out


def _guarded(run, out: Path, call):
    """The run itself. A halt saves the stopped run; so does a crash, as code CRASH."""
    try:
        return call(), None
    except InvariantError as e:
        return None, _save_halt(run, out, e)
    except Exception as e:
        return None, _save_halt(run, out, InvariantError("CRASH", f"{type(e).__name__}: {e}"))


def _axes(raw: str) -> list[str]:
    return [a.strip() for a in raw.split(",") if a.strip()]


def _save_halt(run, out: Path, err: InvariantError) -> int:
    out = Path(out)
    try:
        save_run(run, out)
        saved = str(out)
    except Exception:
        saved = None
    print(json.dumps({
        "ok": False,
        "halt": True,
        "code": err.code,
        "error": str(err),
        "status": getattr(run, "status", None) and run.status.value,
        "stop_reason": getattr(run, "stop_reason", ""),
        "review": getattr(run, "review", None),
        "saved": saved,
    }, indent=2))
    if saved:
        print(f"\nsaved {out}")
    return 1


def _save_done(result, out: Path, **extra) -> int:
    from .diagnostics import DEFAULT_CRITERIA_WARNING, default_criteria

    out = Path(out)
    save_run(result.run, out)
    if default_criteria(result.run):
        extra["warning"] = DEFAULT_CRITERIA_WARNING
    review = {"review": result.run.review} if result.run.review else {}
    print(json.dumps(result.run.summary() | {"product": result.product.claim} | review | extra, indent=2))
    print(f"\nsaved {out}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    store, run, engine, out = _start(args)
    result, halted = _guarded(run, out, lambda: engine.run_task(run, context=args.context, operator_question=args.question))
    if result is None:
        return halted
    gates = [
        {"channel": v.subtask.channel_id, "skill": v.subtask.skill, "legal": v.legal, "refused": v.refused}
        for v in result.verdicts or []
    ]
    return _save_done(result, out, gates=gates, answer=run.notes["question-1"].reason)


def cmd_single(args: argparse.Namespace) -> int:
    store, run, engine, out = _start(args)
    result, halted = _guarded(run, out, lambda: engine.run_single(
        run, context=args.context, operator_question=args.question,
        lead_response=args.response, lead_reason=args.reason,
    ))
    return halted if result is None else _save_done(result, out)


def cmd_fanout(args: argparse.Namespace) -> int:
    store, run, engine, out = _start(args)
    subtasks = parse_subtasks(args.context)
    if not subtasks:
        for part in args.subtasks.split(","):
            if ":" not in part:
                continue
            spec, failure = part.split(":", 1)
            channel, _, skill = spec.partition("@")
            subtasks.append(Subtask(channel.strip(), failure.strip(), skill=skill.strip().lower() or "execute"))
    result, halted = _guarded(run, out, lambda: engine.run_fanout(
        run, context=args.context, subtasks=subtasks, axes=_axes(args.axes),
        operator_question=args.question, lead_response=args.response, lead_reason=args.reason,
    ))
    return halted if result is None else _save_done(result, out, split=result.split)


def cmd_replan(args: argparse.Namespace) -> int:
    store, run, engine, out = _start(args)
    result, halted = _guarded(run, out, lambda: engine.run_replan(
        run, context=args.context, replan_reason=args.replan_reason, new_method=args.method, axes=_axes(args.axes),
    ))
    return halted if result is None else _save_done(result, out)


def cmd_brief(args: argparse.Namespace) -> int:
    from .diagnostics import diagnose
    from .schema import state_contract

    store, run, engine, out = _start(args)
    result, halted = _guarded(run, out, lambda: engine.run_single(run, context=args.context, operator_question=args.question))
    if result is None:
        return halted
    save_run(result.run, out)
    report = diagnose(result.run)
    print(json.dumps({
        "ok": True,
        "state": state_contract(result.run.state),
        "product": result.product.claim if result.product else None,
        "could_this_have_been_one": result.run.state.worker_count() == 0,
        "health": report["health"],
        "tier": report["tier"]["name"],
        "saved": str(out),
    }, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="taskorg", description="Genet — policy-governed agent runtime")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("run", help="the lead reads the context and staffs the task; the gates judge it")
    _add_run_args(
        m,
        id="run-001",
        goal="Complete the task",
        purpose="Keep the goal intact",
        done_when="Task finished",
        context="One source holds everything needed.",
    )
    m.add_argument("--question", default="Could a single agent have done this?")
    m.set_defaults(func=cmd_run)

    r = sub.add_parser("single", help="single agent: read the context, draft, verify")
    _add_run_args(
        r,
        id="single-001",
        goal="Complete the default task",
        purpose="Keep one shared context and one plan",
        done_when="Task recorded and review closed",
        context="The first path is blocked. Two independent sources are visible.",
    )
    r.add_argument("--question", default="Why solve this with one agent instead of splitting the sources?")
    r.add_argument("--response", default="KEEP_ROSTER")
    r.add_argument("--reason", default="The context is enough; no second agent required.")
    r.set_defaults(func=cmd_single)

    s = sub.add_parser("fanout", help="gated fan-out on sub-tasks the operator names")
    _add_run_args(
        s,
        id="fanout-001",
        goal="Complete the task",
        purpose="Keep the goal intact",
        done_when="Task finished",
        context="The first path is blocked. source-a and source-b are independent.",
    )
    s.add_argument("--subtasks", default="source-a:independent source-a channel,source-b:independent source-b channel",
                   help="channel[@skill]:named failure, comma separated; used when --context tags no sub-tasks")
    s.add_argument("--axes", default="parallel,fan_in")
    s.add_argument("--question", default="Why keep one agent if two sources are independent?")
    s.add_argument("--response", default="CHANGE_METHOD")
    s.add_argument("--reason", default="The sources are independent. The method can fan out. The roster stays small.")
    s.set_defaults(func=cmd_fanout)

    a = sub.add_parser("replan", help="the plan is wrong: request a replan and change the method")
    _add_run_args(
        a,
        id="replan-001",
        goal="Complete the task",
        purpose="Keep the goal intact",
        done_when="Task finished",
        context="The first source is stale. The second source is current.",
    )
    a.add_argument("--replan-reason", default="The first plan no longer fits: the first source is stale")
    a.add_argument("--method", default="work from source-b")
    a.add_argument("--axes", default="reroute")
    a.set_defaults(func=cmd_replan)

    p_b = sub.add_parser("brief", help="goal + purpose + context in, run state and health out")
    _add_run_args(
        p_b,
        required=("goal", "purpose", "context"),
        id="brief-001",
        done_when="Goal met",
    )
    p_b.add_argument("--question", default="Could a single agent have done this?")
    p_b.set_defaults(func=cmd_brief)

    p_replay = sub.add_parser("replay", help="print a saved run log")
    p_replay.add_argument("path")
    p_replay.set_defaults(func=cmd_replay)

    p_ins = sub.add_parser("inspect", help="run state and the last log events")
    p_ins.add_argument("path")
    p_ins.set_defaults(func=cmd_inspect)

    p_board = sub.add_parser("board", help="one-screen summary of a saved run")
    p_board.add_argument("path")
    p_board.set_defaults(func=cmd_board)

    p_bench = sub.add_parser("bench", help="score the fixtures in fixtures/bench against their expect blocks")
    p_bench.add_argument("--fixtures", default=None, help="directory of bench fixtures (default: the repo's)")
    p_bench.set_defaults(func=cmd_bench)

    p_c = sub.add_parser("compare", help="single agent vs always-split crew vs genet on the synthetic suite")
    p_c.add_argument("--adapter", default="stub", choices=["stub", "sim", "live", "anthropic"],
                     help="stub: plumbing only; sim: deterministic reader, structural cost at $0; "
                          "live: an OpenAI-compatible endpoint; anthropic: Claude's Messages API")
    p_c.add_argument("--strategies", default="single,always,genet")
    p_c.add_argument("--families", default="lookup,aggregate,compare,breadth")
    p_c.add_argument("--per-family", type=_whole(1), default=5)
    p_c.add_argument("--entities", type=_whole(2), default=None,
                     help="companies per aggregate and breadth question, from a larger pool (default 3 and 5)")
    p_c.add_argument("--distractors", type=_whole(0), default=0, help="extra wrong-year figures per company")
    p_c.add_argument("--filed", type=_whole(0), default=0,
                     help="companies per aggregate and breadth question already filed, checked, in filed.md")
    p_c.add_argument("--repeat", type=_whole(1), default=1)
    p_c.add_argument("--seed", type=int, default=7)
    p_c.add_argument("--max-calls", type=_whole(1), default=40, help="per-trial call cap, same for every strategy")
    p_c.add_argument("--context", type=_whole(1), default=16_000, help="per-call token cap, same for every strategy")
    p_c.add_argument("--tool-rounds", type=_whole(0), default=3)
    p_c.add_argument("--price-in", type=_finite(0, strict=False), default=None, help="$ per 1M input tokens, for cost columns")
    p_c.add_argument("--price-out", type=_finite(0, strict=False), default=None, help="$ per 1M output tokens")
    p_c.add_argument("--corpus", default=None, help="also write the corpus here, to read it")
    p_c.add_argument("--max-spend", type=_finite(0, strict=True), default=None,
                     help="$ cap: stop before a trial that could pass it (needs --price-in and --price-out)")
    p_c.add_argument("--record", default=None, help="save every model exchange to this tape, to replay with no key")
    p_c.add_argument("--replay", default=None, help="answer from this tape instead of a model: no key, no spend")
    p_c.add_argument("--out", default=None, help="results JSON (default data/compare/compare-<time>.json)")
    p_c.add_argument("--verify-view", default="independent", choices=list(VIEWS),
                     help="what the verifier sees: shared (every note), independent (not the author's notes)")
    p_c.add_argument("--verify-sources", default="layered", choices=list(SOURCES),
                     help="sources the kernel opens for the verifier: layered (default), full, or none "
                          "(the brief before v0.7.0, which older tapes replay)")
    p_c.add_argument("--verify-rule", default="both", choices=list(MERGE_RULES),
                     help="words after the verifier's source rule, with sources open: both (the default), told, headed, named, aside, "
                          "or none (the brief before v0.10.0, which older tapes replay). merge-bench says what each is")
    p_c.add_argument("--no-rework-reason", dest="rework_reason", action="store_false",
                     help="leave out of the lead's rework brief why the verifier failed its product (as older tapes hold it)")
    p_c.add_argument("--author-rule", default="none", choices=list(AUTHOR_RULES),
                     help="words for the lead's and sub-agents' briefs: none (the default), or headed, a line that gives no "
                          "year takes the year in its file's heading")
    p_c.add_argument("--gap-check", action="store_true",
                     help="send back, once, a product the verifier passed that says itself it has no figure for something, adds 0 "
                          "for it or set it aside; a reworked product that still says so stops the run. Off by default")
    p_c.add_argument("--price", action="append", default=[], metavar="MODEL=IN/OUT",
                     help="$ per 1M tokens for one model, input/output, for a team that mixes models; repeat for each")
    p_c.add_argument("--then-live", action="store_true",
                     help="with --replay and --record: answer from the tape until the gap check sends a product back, "
                          "then send that trial's later requests to the model (--adapter anthropic) and record them")
    p_c.add_argument("--benchmark", default=None, choices=["loong", "hotpot"],
                     help="a public benchmark's questions in place of the generated suite (docs/HEAD_TO_HEAD.md): loong needs "
                          "--questions and --docs, hotpot --questions; --families and the suite options are then not used")
    p_c.add_argument("--questions", default=None, help="the benchmark's question file (JSON lines)")
    p_c.add_argument("--docs", default=None, help="Loong's doc/financial folder")
    p_c.add_argument("--which", default="main", choices=["main", "calibration"],
                     help="Loong's planned sample: 40 main questions, or the 4 for calibration")
    p_c.add_argument("--ids", default=None,
                     help="with --benchmark: only these questions of the sample, by task id (loong-1a2b3c4d), comma separated")
    p_c.add_argument("--page-chars", type=_whole(1000), default=None,
                     help="read long files a page of this many characters at a time (read:PATH@N). Off by default")
    p_c.add_argument("--max-seconds", type=_finite(1, strict=False), default=600.0,
                     help="per-trial wall-clock cap, same for every strategy")
    p_c.add_argument("--dry-run", action="store_true", help="print the plan and call ceiling; call no model")
    p_c.set_defaults(func=cmd_compare)

    p_j = sub.add_parser("h2h-judge", help="score Loong answers with Loong's own judge prompt (docs/HEAD_TO_HEAD.md)")
    p_j.add_argument("--results", action="append", required=True, help="a results JSON (compare's or the CrewAI harness's); repeat")
    p_j.add_argument("--questions", required=True, help="Loong's question file")
    p_j.add_argument("--model", default="claude-sonnet-5-5", help="the judge, a model other than the one under test")
    p_j.add_argument("--call-limit", type=_whole(2000), default=16_000)
    p_j.add_argument("--price-in", type=_finite(0, strict=False), default=None, help="$ per 1M input tokens, the judge's")
    p_j.add_argument("--price-out", type=_finite(0, strict=False), default=None)
    p_j.add_argument("--max-spend", type=_finite(0, strict=True), default=None, help="$ cap (needs --price-in and --price-out)")
    p_j.add_argument("--record", default=None, help="save every judge exchange to this raw tape")
    p_j.add_argument("--replay", default=None, help="score from this raw tape: no key, no spend")
    p_j.add_argument("--out", required=True, help="the judged results JSON")
    p_j.set_defaults(func=cmd_h2h_judge)

    p_v = sub.add_parser("verify-bench", help="does the verifier catch a wrong product? products with planted errors")
    p_v.add_argument("--adapter", default="sim", choices=["stub", "sim", "live", "anthropic"],
                     help="sim: a perfect checker of what it is shown, at $0; live or anthropic: a real model")
    p_v.add_argument("--setups", default=",".join(VERIFY_DEFAULT_SETUPS),
                     help=f"from {', '.join(VERIFY_SETUPS)}; default {', '.join(VERIFY_DEFAULT_SETUPS)}")
    p_v.add_argument("--arms", default="plain", help=f"from {', '.join(VERIFY_ARMS)}: plain; note, where the author's note "
                     "argues for the planted figure (wrong products only); planted, where every file the goal names "
                     "carries an instruction to the verifier; split, products shaped like a lead's merge")
    p_v.add_argument("--questions", type=_whole(1), default=6, help="aggregate questions; four products each, two wrong")
    p_v.add_argument("--entities", type=_whole(2), default=20, help="companies per question")
    p_v.add_argument("--distractors", type=_whole(0), default=6, help="extra wrong-year figures per company")
    p_v.add_argument("--repeat", type=_whole(1), default=1)
    p_v.add_argument("--seed", type=int, default=7)
    p_v.add_argument("--max-calls", type=_whole(1), default=4, help="per-review call cap")
    p_v.add_argument("--context", type=_whole(1), default=200_000, help="per-call token cap")
    p_v.add_argument("--price-in", type=_finite(0, strict=False), default=None, help="$ per 1M input tokens")
    p_v.add_argument("--price-out", type=_finite(0, strict=False), default=None, help="$ per 1M output tokens")
    p_v.add_argument("--max-spend", type=_finite(0, strict=True), default=None,
                     help="$ cap: stop before a review that could pass it (needs --price-in and --price-out)")
    p_v.add_argument("--record", default=None, help="save every model exchange to this tape")
    p_v.add_argument("--replay", default=None, help="answer from this tape: no key, no spend")
    p_v.add_argument("--corpus", default=None, help="also write the corpus here, to read it")
    p_v.add_argument("--out", default=None, help="results JSON (default data/compare/verify-<time>.json)")
    p_v.add_argument("--dry-run", action="store_true", help="print the plan; call no model")
    p_v.set_defaults(func=cmd_verify_bench)

    p_m = sub.add_parser("merge-bench", help="does the verifier fail a real merge? the tapes' merges, reviewed under each rule")
    p_m.add_argument("--tapes", required=True, help="the tapes to take merges from, comma separated")
    p_m.add_argument("--adapter", default="sim", choices=["stub", "sim", "live", "anthropic"],
                     help="sim: at $0; live or anthropic: a real verifier")
    p_m.add_argument("--rules", default=",".join(MERGE_RULES), help=f"from {', '.join(MERGE_RULES)}")
    p_m.add_argument("--repeat", type=_whole(1), default=1)
    p_m.add_argument("--workers", type=_whole(1), default=1, help="reviews at the same time")
    p_m.add_argument("--price-in", type=_finite(0, strict=False), default=None, help="$ per 1M input tokens")
    p_m.add_argument("--price-out", type=_finite(0, strict=False), default=None, help="$ per 1M output tokens")
    p_m.add_argument("--max-spend", type=_finite(0, strict=True), default=None,
                     help="$ cap: stop before a review that could pass it (needs --price-in and --price-out)")
    p_m.add_argument("--record", default=None, help="save every model exchange to this tape")
    p_m.add_argument("--replay", default=None, help="answer from this tape: no key, no spend")
    p_m.add_argument("--out", default=None, help="results JSON (default data/compare/merges-<time>.json)")
    p_m.add_argument("--dry-run", action="store_true", help="print the plan; call no model")
    p_m.set_defaults(func=cmd_merge_bench)

    p_w = sub.add_parser("rework-bench", help="told why the verifier failed its product, does a lead put it right? the tapes' reworks, asked again")
    p_w.add_argument("--tapes", required=True, help="the tapes to take reworks from, comma separated")
    p_w.add_argument("--adapter", default="sim", choices=["stub", "sim", "live", "anthropic"],
                     help="sim: at $0; live or anthropic: a real lead")
    p_w.add_argument("--arms", default="plain,reason", help="from plain, reason")
    p_w.add_argument("--repeat", type=_whole(1), default=1)
    p_w.add_argument("--workers", type=_whole(1), default=1, help="reworks at the same time")
    p_w.add_argument("--price-in", type=_finite(0, strict=False), default=None, help="$ per 1M input tokens")
    p_w.add_argument("--price-out", type=_finite(0, strict=False), default=None, help="$ per 1M output tokens")
    p_w.add_argument("--max-spend", type=_finite(0, strict=True), default=None,
                     help="$ cap: stop before a rework that could pass it (needs --price-in and --price-out)")
    p_w.add_argument("--record", default=None, help="save every model exchange to this tape")
    p_w.add_argument("--replay", default=None, help="answer from this tape: no key, no spend")
    p_w.add_argument("--out", default=None, help="results JSON (default data/compare/reworks-<time>.json)")
    p_w.add_argument("--dry-run", action="store_true", help="print the plan; call no model")
    p_w.set_defaults(func=cmd_rework_bench)

    p_p = sub.add_parser("plan-bench", help="does a second plan fit? first plans the gates refuse, and the lead's next")
    p_p.add_argument("--adapter", default="sim", choices=["stub", "sim", "live", "anthropic"],
                     help="sim: at $0; live or anthropic: a real lead")
    p_p.add_argument("--shapes", default=",".join(PLAN_SHAPES), help=f"first plans, from {', '.join(PLAN_SHAPES)}")
    p_p.add_argument("--questions", type=_whole(1), default=3, help="questions of each family, aggregate and breadth")
    p_p.add_argument("--distractors", type=_whole(0), default=6, help="extra wrong-year figures per company")
    p_p.add_argument("--repeat", type=_whole(1), default=1)
    p_p.add_argument("--seed", type=int, default=7)
    p_p.add_argument("--max-calls", type=_whole(1), default=40, help="per-trial call cap, as a run's")
    p_p.add_argument("--context", type=_whole(1), default=8_000, help="per-call token cap")
    p_p.add_argument("--tool-rounds", type=_whole(0), default=4, help="tool rounds a sub-agent would get")
    p_p.add_argument("--price-in", type=_finite(0, strict=False), default=None, help="$ per 1M input tokens")
    p_p.add_argument("--price-out", type=_finite(0, strict=False), default=None, help="$ per 1M output tokens")
    p_p.add_argument("--max-spend", type=_finite(0, strict=True), default=None,
                     help="$ cap: stop before a plan that could pass it (needs --price-in and --price-out)")
    p_p.add_argument("--record", default=None, help="save every model exchange to this tape")
    p_p.add_argument("--replay", default=None, help="answer from this tape: no key, no spend")
    p_p.add_argument("--corpus", default=None, help="also write the corpus here, to read it")
    p_p.add_argument("--out", default=None, help="results JSON (default data/compare/plan-<time>.json)")
    p_p.add_argument("--dry-run", action="store_true", help="print the plan; call no model")
    p_p.set_defaults(func=cmd_plan_bench)

    p_r = sub.add_parser("report-bench", help="does a sub-agent hand back a part the plan got wrong? parts with planted errors")
    p_r.add_argument("--adapter", default="sim", choices=["stub", "sim", "live", "anthropic"],
                     help="sim: a perfect sub-agent, at $0; live or anthropic: a real model")
    p_r.add_argument("--setups", default=",".join(REPORT_SETUPS), help=f"from {', '.join(REPORT_SETUPS)}")
    p_r.add_argument("--questions", type=_whole(1), default=6, help="aggregate questions; four parts each, two wrong")
    p_r.add_argument("--entities", type=_whole(2), default=20, help="companies per question")
    p_r.add_argument("--distractors", type=_whole(0), default=6, help="extra wrong-year figures per company")
    p_r.add_argument("--repeat", type=_whole(1), default=1)
    p_r.add_argument("--seed", type=int, default=7)
    p_r.add_argument("--max-calls", type=_whole(1), default=4, help="per-part call cap")
    p_r.add_argument("--context", type=_whole(1), default=200_000, help="per-call token cap")
    p_r.add_argument("--price-in", type=_finite(0, strict=False), default=None, help="$ per 1M input tokens")
    p_r.add_argument("--price-out", type=_finite(0, strict=False), default=None, help="$ per 1M output tokens")
    p_r.add_argument("--max-spend", type=_finite(0, strict=True), default=None,
                     help="$ cap: stop before a part that could pass it (needs --price-in and --price-out)")
    p_r.add_argument("--record", default=None, help="save every model exchange to this tape")
    p_r.add_argument("--replay", default=None, help="answer from this tape: no key, no spend")
    p_r.add_argument("--corpus", default=None, help="also write the corpus here, to read it")
    p_r.add_argument("--out", default=None, help="results JSON (default data/compare/report-<time>.json)")
    p_r.add_argument("--dry-run", action="store_true", help="print the plan; call no model")
    p_r.set_defaults(func=cmd_report_bench)

    p_d = sub.add_parser("diagnose", help="performance and interaction at every level")
    p_d.add_argument("path")
    p_d.set_defaults(func=cmd_diagnose)

    p_pol = sub.add_parser("policy-replay", help="label a saved log for the policy head")
    p_pol.add_argument("path")
    p_pol.set_defaults(func=cmd_policy_replay)
    p_fit = sub.add_parser("policy-fit", help="fit the tiny imitation head offline")
    p_fit.add_argument("--out", default="data/policy/imitation.json")
    p_fit.set_defaults(func=cmd_policy_fit)
    p_rl = sub.add_parser("policy-rl", help="sparse RL vs stub on bench-shaped boards")
    p_rl.add_argument("--episodes", type=_whole(1), default=60)
    p_rl.set_defaults(func=cmd_policy_rl)
    p_sft = sub.add_parser("policy-sft", help="write chat JSONL for a later model trainer")
    p_sft.add_argument("--out", default="data/policy/sft.jsonl")
    p_sft.add_argument("--n", type=_whole(1), default=240)
    p_sft.set_defaults(func=cmd_policy_sft)
    p_ft = sub.add_parser("policy-finetune", help="fine-tune the local policy head on the SFT corpus")
    p_ft.add_argument("--out", default="data/policy/imitation.json")
    p_ft.set_defaults(func=cmd_policy_finetune)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except InvariantError as e:
        print(json.dumps({"ok": False, "halt": True, "code": e.code, "error": str(e)}, indent=2))
        return 1
    except OSError as e:  # a path that is missing, a directory, or not writable
        print(json.dumps({"ok": False, "halt": True, "code": "IO", "error": f"{type(e).__name__}: {e}"}, indent=2))
        return 1


def _model_source(args: argparse.Namespace, config: dict, header_key: str, code: str, keys: tuple[str, ...]):
    """The adapter each trial gets: a tape's replies (--replay), or a model, whose exchanges --record saves.
    Returns (factory, player, recorder). A replayed tape whose recorded settings differ is noted."""
    from .compare import stderr

    player = recorder = None
    if getattr(args, "then_live", False):
        return _continuing_source(args, config, header_key, code)
    if args.replay:
        from .tape import Player, replay_adapter

        player = Player(Path(args.replay))
        recorded = player.header.get(header_key)
        recorded = recorded if isinstance(recorded, dict) else {}
        if recorded:  # A tape from before a switch does not name it, and was recorded without it.
            recorded = {"verify_rule": "none", "rework_reason": False, "gap_check": False} | recorded
        differ = [k for k in keys if k in recorded and recorded[k] != config.get(k)]
        if differ:
            stderr(f"note: the tape was recorded with a different {', '.join(differ)}; expect requests it does not have")
        config |= {"tape": str(args.replay), "replayed": player.header.get("adapter"), "model": player.header.get("model")}

        def factory():
            return replay_adapter(player)
    else:
        first = pick_adapter(args.adapter)  # fail fast on missing live configuration
        if args.record:
            if not hasattr(first, "tape_header"):
                raise InvariantError(code, "--record needs a model adapter: live or anthropic")
            from .tape import Recorder

            config["model"] = first.model
            if getattr(first, "cache", False):
                config["cache"] = True
            recorder = Recorder(Path(args.record), first.tape_header() | {header_key: dict(config)})
            config["tape"] = str(args.record)

        def factory():
            adapter = pick_adapter(args.adapter)
            if recorder:
                adapter.tape = recorder
            return adapter
    return factory, player, recorder


def _model_prices(raw: list[str]) -> dict[str, tuple[float, float]]:
    """--price MODEL=IN/OUT, each repeat one model."""
    out = {}
    for item in raw:
        try:
            model, rates = item.split("=", 1)
            price_in, price_out = (float(x) for x in rates.split("/"))
        except ValueError:
            raise InvariantError("COMPARE", f"--price takes MODEL=IN/OUT, got {item!r}") from None
        if not model.strip() or price_in < 0 or price_out < 0 or not math.isfinite(price_in + price_out):
            raise InvariantError("COMPARE", f"--price takes MODEL=IN/OUT with prices of 0 or more, got {item!r}")
        out[model.strip()] = (price_in, price_out)
    return out


def _continuing_source(args: argparse.Namespace, config: dict, header_key: str, code: str):
    """--then-live: each trial replays its tape until the gap check sends a product back, then goes to the model. The
    live adapter must be the one the tape was recorded with, so the requests before that point are the same."""
    from .loop import GAP_ARM
    from .tape import Continuing, LiveSpend, Player, Recorder

    if not (args.replay and args.record and args.adapter == "anthropic" and args.gap_check):
        raise InvariantError(code, "--then-live needs --replay, --record, --adapter anthropic and --gap-check")
    player = Player(Path(args.replay))
    h = player.header
    first = pick_adapter(args.adapter)  # fails fast with no key or model
    same = (h.get("adapter") == first.name and h.get("model") == first.model and h.get("effort") == first.effort
            and dict(h.get("models") or {}) == dict(first.models))
    if not same:
        raise InvariantError(code, f"--then-live needs the tape's model and effort ({h.get('model')}, {h.get('effort')}); "
                                   f"the environment gives {first.model}, {first.effort}")
    rounds = h.get("round_reply_tokens") or 0
    config |= {"tape": str(args.replay), "replayed": h.get("adapter"), "model": h.get("model"), "then_live": True,
               "live_tape": str(args.record)}
    first.round_reply_tokens = rounds
    recorder = Recorder(Path(args.record), first.tape_header() | {header_key: dict(config)})
    spend = LiveSpend()

    def factory():
        adapter = pick_adapter(args.adapter)
        adapter.round_reply_tokens = rounds  # what the tape's rounds kept, so its requests are the same
        adapter.tape = Continuing(player, recorder, GAP_ARM, spend)
        return adapter

    factory.spend = spend
    return factory, player, recorder


def _benchmark_suite(args: argparse.Namespace):
    """A public benchmark's questions (taskorg/benchmarks.py), from files the operator downloaded."""
    from . import benchmarks

    if not args.questions:
        raise InvariantError("COMPARE", f"--benchmark {args.benchmark} needs --questions")
    if args.benchmark == "loong":
        if not args.docs:
            raise InvariantError("COMPARE", "--benchmark loong needs --docs, Loong's doc/financial folder")
        suite = benchmarks.loong_suite(args.questions, args.docs, args.which)
    else:
        suite = benchmarks.hotpot_suite(args.questions)
    if args.ids:
        wanted = [i.strip() for i in args.ids.split(",") if i.strip()]
        known = {t.id for t in suite.tasks}
        unknown = [i for i in wanted if i not in known]
        if unknown or not wanted:
            named = ", ".join(unknown) if unknown else repr(args.ids)
            raise InvariantError("COMPARE", f"--ids names no question of this sample: {named}")
        suite.tasks = [t for t in suite.tasks if t.id in set(wanted)]
    return suite


def cmd_h2h_judge(args: argparse.Namespace) -> int:
    from collections import defaultdict

    from . import atomic
    from .benchmarks import read_jsonl
    from .compare import stderr
    from .judge import judge_rows
    from .rawcall import RawClient, RawPlayer, RawTape, Spend

    if (args.price_in is None) != (args.price_out is None):
        raise InvariantError("H2H", "give both --price-in and --price-out, or neither")
    if args.max_spend is not None and args.price_in is None:
        raise InvariantError("H2H", "--max-spend needs --price-in and --price-out")
    if args.record and args.replay:
        raise InvariantError("H2H", "--record or --replay, not both")
    rows: list[dict] = []
    for path in args.results:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rows += [r | {"source": str(path)} for r in data["results"]]
    spend = Spend(default=(args.price_in or 0.0, args.price_out or 0.0))
    config = {"model": args.model, "results": args.results, "call_limit": args.call_limit}
    if args.replay:
        client = RawClient(call_limit=args.call_limit, player=RawPlayer(args.replay), spend=spend, effort=None)
        config["replay"] = args.replay
    else:
        tape = RawTape(args.record, {"adapter": "anthropic-raw", "model": args.model, "purpose": "h2h-judge"}) if args.record else None
        client = RawClient.live(call_limit=args.call_limit, tape=tape, spend=spend, max_spend=args.max_spend, effort=None)
        config["record"] = args.record
    try:
        judged = judge_rows(rows, read_jsonl(args.questions), client, args.model, progress=stderr)
    finally:
        if client.tape:
            client.tape.close()
    atomic.write_text(Path(args.out), json.dumps({"config": config, "results": judged}, indent=2, ensure_ascii=False))
    table: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for r in judged:
        if "judge_score" in r:
            t = table[r.get("strategy", "?")]
            t[0] += 1
            t[1] += bool(r["correct"])
            t[2] += bool(r["answer_right"])
            t[3] += int(r["judge_score"] or 0)
    print("| strategy | judged | right | right answer | mean score |\n|---|---|---|---|---|")
    for name, (n, right, answer, total) in sorted(table.items()):
        print(f"| {name} | {n} | {right} | {answer} | {total / n:.1f} |")
    print(f"judge calls sent: {spend.calls}" + (f", ${spend.dollars:.4f}" if args.price_in is not None else ""))
    print(f"saved {args.out}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    import time

    from .compare import (STRATEGIES, comparison_budget, live_spend_cap, render, run_comparison, save, spend_cap, stderr,
                          summarize)
    from .suite import FAMILIES, build_suite

    # Each once: a repeat would run every trial twice, or give two tasks the same id.
    strategies = tuple(dict.fromkeys(s.strip() for s in args.strategies.split(",") if s.strip()))
    families = tuple(dict.fromkeys(f.strip() for f in args.families.split(",") if f.strip()))
    if not strategies or not families:
        raise InvariantError("COMPARE", "name at least one strategy and one family")
    bad = (set(strategies) - set(STRATEGIES)) | (set(families) - set(FAMILIES))
    if bad:
        raise InvariantError("COMPARE", f"unknown strategy or family: {sorted(bad)}")
    out = _out_path(args.out, Path(f"data/compare/compare-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    if (args.price_in is None) != (args.price_out is None):
        raise InvariantError("COMPARE", "give both --price-in and --price-out, or neither")
    if args.max_spend is not None and args.price_in is None:
        raise InvariantError("COMPARE", "--max-spend needs --price-in and --price-out")
    prices = _model_prices(args.price)
    if prices and args.price_in is None:
        raise InvariantError("COMPARE", "--price needs --price-in and --price-out, for tokens no model is named for")
    if args.record and args.replay and not args.then_live:
        raise InvariantError("COMPARE", "--record or --replay, not both, unless --then-live")
    from .tools import PAGE_MAX
    if args.page_chars is not None and args.page_chars > PAGE_MAX:
        raise InvariantError("COMPARE", f"--page-chars is at most {PAGE_MAX:,}")
    if args.ids and not args.benchmark:
        raise InvariantError("COMPARE", "--ids picks questions of a --benchmark sample")
    try:
        if args.benchmark:
            suite = _benchmark_suite(args)
        else:
            suite = build_suite(seed=args.seed, per_family=args.per_family, families=families,
                                entities=args.entities, distractors=args.distractors, filed=args.filed)
    except (ValueError, OSError) as e:
        raise InvariantError("COMPARE", str(e)) from None
    trials = len(suite.tasks) * len(strategies) * args.repeat
    config = {
        "adapter": "replay" if args.replay else args.adapter, "strategies": list(strategies), "families": list(families),
        "per_family": args.per_family, "repeat": args.repeat, "seed": args.seed,
        "entities": args.entities, "distractors": args.distractors, "filed": args.filed,
        "max_calls_per_trial": args.max_calls, "context_tokens": args.context, "tool_rounds": args.tool_rounds,
        "verify_view": args.verify_view, "verify_sources": args.verify_sources, "verify_rule": args.verify_rule,
        "rework_reason": args.rework_reason, "author_rule": args.author_rule, "gap_check": args.gap_check,
        "trials": trials, "call_ceiling": trials * args.max_calls,
    }
    # Only a benchmark run names these, so a generated-suite run's config, and its tape, read as before.
    bench_keys = ("benchmark", "which", "page_chars", "max_seconds") if args.benchmark else ()
    if args.benchmark:
        config |= {"benchmark": args.benchmark, "which": args.which if args.benchmark == "loong" else None,
                   "page_chars": args.page_chars, "max_seconds": args.max_seconds,
                   "task_ids": [t.id for t in suite.tasks]}
        for k in ("families", "per_family", "seed", "entities", "distractors", "filed"):
            config[k] = None
    elif args.page_chars is not None or args.max_seconds != 600.0:
        config |= {"page_chars": args.page_chars, "max_seconds": args.max_seconds}
        bench_keys = ("page_chars", "max_seconds")
    if args.price_in is not None:
        config |= {"price_in": args.price_in, "price_out": args.price_out}
    if args.max_spend is not None:
        config["max_spend"] = args.max_spend
    if prices:
        config["prices"] = {m: list(p) for m, p in prices.items()}
    if args.dry_run:
        print(json.dumps(config | {"tasks": [t.question for t in suite.tasks]}, indent=2))
        return 0
    factory, player, recorder = _model_source(
        args, config, "compare", "COMPARE",
        ("strategies", "families", "per_family", "repeat", "seed", "entities", "distractors", "filed",
         "max_calls_per_trial", "context_tokens", "tool_rounds", "verify_view", "verify_sources", "verify_rule",
         "rework_reason", "author_rule", "gap_check") + bench_keys,
    )
    if args.corpus:
        suite.write_corpus(args.corpus)
    try:
        results = run_comparison(
            suite,
            factory,
            strategies=strategies,
            repeats=args.repeat,
            budget_factory=lambda: comparison_budget(args.max_calls, args.context, args.max_seconds),
            tool_rounds=args.tool_rounds,
            corpus_dir=Path(args.corpus) if args.corpus else None,
            progress=stderr,
            stop_when=(None if args.max_spend is None
                       else live_spend_cap(factory.spend, args.max_spend, args.price_in, args.price_out) if args.then_live
                       else spend_cap(args.max_spend, args.price_in, args.price_out, prices)),
            verify={"verify_view": args.verify_view, "verify_sources": args.verify_sources,
                    "verify_note": MERGE_RULES[args.verify_rule], "rework_reason": args.rework_reason,
                    "author_note": AUTHOR_RULES[args.author_rule], "gap_check": args.gap_check},
            page_chars=args.page_chars,
        )
    finally:
        if recorder:
            recorder.close()
    if len(results) < trials:
        config["stopped_after"] = len(results)
    summary = summarize(results, price_in=args.price_in, price_out=args.price_out, prices=prices)
    save(out, config=config, results=results, summary=summary)
    print(render(summary))
    if player:
        print(f"replay: {player.served} replies served ({player.repeated} repeated), "
              f"{player.misses} requests the tape does not have")
    if args.then_live:
        spend = factory.spend
        live = (f", ${spend.cost(args.price_in, args.price_out):.4f}" if args.price_in is not None else "")
        print(f"live: {spend.calls} requests sent to the model after the gap check{live}")
    if recorder:
        print(f"tape: {recorder.count} exchanges saved to {args.record}")
    print(f"saved {out}")
    return 0


def cmd_verify_bench(args: argparse.Namespace) -> int:
    import time

    from .compare import comparison_budget, spend_cap, stderr
    from .suite import build_suite
    from .verify_bench import products, render, run_bench, save, summarize

    setups = tuple(dict.fromkeys(s.strip() for s in args.setups.split(",") if s.strip()))
    bad = set(setups) - set(VERIFY_SETUPS)
    if not setups or bad:
        raise InvariantError("VERIFY_BENCH", f"name setups from {list(VERIFY_SETUPS)}" + (f"; unknown: {sorted(bad)}" if bad else ""))
    arms = tuple(dict.fromkeys(a.strip() for a in args.arms.split(",") if a.strip()))
    bad = set(arms) - set(VERIFY_ARMS)
    if not arms or bad:
        raise InvariantError("VERIFY_BENCH", f"name arms from {list(VERIFY_ARMS)}" + (f"; unknown: {sorted(bad)}" if bad else ""))
    if (args.price_in is None) != (args.price_out is None):
        raise InvariantError("VERIFY_BENCH", "give both --price-in and --price-out, or neither")
    if args.max_spend is not None and args.price_in is None:
        raise InvariantError("VERIFY_BENCH", "--max-spend needs --price-in and --price-out")
    if args.record and args.replay:
        raise InvariantError("VERIFY_BENCH", "--record or --replay, not both")
    try:
        suite = build_suite(seed=args.seed, per_family=args.questions, families=("aggregate",),
                            entities=args.entities, distractors=args.distractors)
    except ValueError as e:
        raise InvariantError("VERIFY_BENCH", str(e)) from None
    items = products(suite, arms)
    reviews = len(items) * len(setups) * args.repeat
    out = _out_path(args.out, Path(f"data/compare/verify-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    config = {
        "adapter": "replay" if args.replay else args.adapter, "setups": list(setups), "arms": list(arms), "questions": args.questions,
        "entities": args.entities, "distractors": args.distractors, "repeat": args.repeat, "seed": args.seed,
        "max_calls_per_review": args.max_calls, "context_tokens": args.context,
        "products": len(items), "wrong_products": sum(b.error is not None for _, _, b in items), "reviews": reviews,
    }
    if args.price_in is not None:
        config |= {"price_in": args.price_in, "price_out": args.price_out}
    if args.max_spend is not None:
        config["max_spend"] = args.max_spend
    if args.dry_run:
        print(json.dumps(config, indent=2))
        return 0
    factory, player, recorder = _model_source(
        args, config, "verify_bench", "VERIFY_BENCH",
        ("setups", "questions", "entities", "distractors", "repeat", "seed", "max_calls_per_review", "context_tokens"),
    )
    if args.corpus:
        suite.write_corpus(args.corpus)
    try:
        results = run_bench(
            suite, factory, setups=setups, arms=arms, repeats=args.repeat,
            budget_factory=lambda: comparison_budget(args.max_calls, args.context),
            corpus_dir=Path(args.corpus) if args.corpus else None, progress=stderr,
            stop_when=spend_cap(args.max_spend, args.price_in, args.price_out) if args.max_spend is not None else None,
        )
    finally:
        if recorder:
            recorder.close()
    if len(results) < reviews:
        config["stopped_after"] = len(results)
    summary = summarize(results, price_in=args.price_in, price_out=args.price_out)
    save(out, config=config, results=results, summary=summary)
    print(render(summary))
    if player:
        print(f"replay: {player.served} replies served ({player.repeated} repeated), "
              f"{player.misses} requests the tape does not have")
    if recorder:
        print(f"tape: {recorder.count} exchanges saved to {args.record}")
    print(f"saved {out}")
    return 0


def cmd_merge_bench(args: argparse.Namespace) -> int:
    import time

    from .compare import spend_cap, stderr
    from .merge_bench import merges_from, render, run_bench, save, summarize

    rules = tuple(dict.fromkeys(r.strip() for r in args.rules.split(",") if r.strip()))
    bad = set(rules) - set(MERGE_RULES)
    if not rules or bad:
        raise InvariantError("MERGE_BENCH", f"name rules from {list(MERGE_RULES)}" + (f"; unknown: {sorted(bad)}" if bad else ""))
    if (args.price_in is None) != (args.price_out is None):
        raise InvariantError("MERGE_BENCH", "give both --price-in and --price-out, or neither")
    if args.max_spend is not None and args.price_in is None:
        raise InvariantError("MERGE_BENCH", "--max-spend needs --price-in and --price-out")
    if args.record and args.replay:
        raise InvariantError("MERGE_BENCH", "--record or --replay, not both")
    tapes = [t.strip() for t in args.tapes.split(",") if t.strip()]
    missing = [t for t in tapes if not Path(t).is_file()]
    if not tapes or missing:
        raise InvariantError("MERGE_BENCH", f"--tapes names no tape it can read: {missing or 'none given'}")
    merges = [m for t in tapes for m in merges_from(Path(t))]
    if not merges:
        raise InvariantError("MERGE_BENCH", "those tapes hold no merge reviewed under the independent view with sources")
    reviews = len(merges) * len(rules) * args.repeat
    out = _out_path(args.out, Path(f"data/compare/merges-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    config = {
        "adapter": "replay" if args.replay else args.adapter, "rules": list(rules), "tapes": [Path(t).name for t in tapes],
        "merges": len(merges), "right": sum(m.right for m in merges), "recorded_fail": sum(m.right and m.recorded == "FAIL" for m in merges),
        "repeat": args.repeat, "reviews": reviews,
    }
    if args.price_in is not None:
        config |= {"price_in": args.price_in, "price_out": args.price_out}
    if args.max_spend is not None:
        config["max_spend"] = args.max_spend
    if args.dry_run:
        print(json.dumps(config, indent=2))
        return 0
    factory, player, recorder = _model_source(args, config, "merge_bench", "MERGE_BENCH", ("rules", "tapes", "repeat"))
    try:
        results = run_bench(merges, factory, rules=rules, repeats=args.repeat, workers=args.workers, progress=stderr,
                            stop_when=spend_cap(args.max_spend, args.price_in, args.price_out) if args.max_spend is not None else None)
    finally:
        if recorder:
            recorder.close()
    if len(results) < reviews:
        config["stopped_after"] = len(results)
    summary = summarize(results, price_in=args.price_in, price_out=args.price_out)
    save(out, config=config, results=results, summary=summary)
    print(render(summary))
    if player:
        print(f"replay: {player.served} replies served ({player.repeated} repeated), "
              f"{player.misses} requests the tape does not have")
    if recorder:
        print(f"tape: {recorder.count} exchanges saved to {args.record}")
    print(f"saved {out}")
    return 0


def cmd_rework_bench(args: argparse.Namespace) -> int:
    import time

    from .compare import spend_cap, stderr
    from .rework_bench import ARMS, render, reworks_from, run_bench, save, summarize

    arms = tuple(dict.fromkeys(a.strip() for a in args.arms.split(",") if a.strip()))
    bad = set(arms) - set(ARMS)
    if not arms or bad:
        raise InvariantError("REWORK_BENCH", f"name arms from {list(ARMS)}" + (f"; unknown: {sorted(bad)}" if bad else ""))
    if (args.price_in is None) != (args.price_out is None):
        raise InvariantError("REWORK_BENCH", "give both --price-in and --price-out, or neither")
    if args.max_spend is not None and args.price_in is None:
        raise InvariantError("REWORK_BENCH", "--max-spend needs --price-in and --price-out")
    if args.record and args.replay:
        raise InvariantError("REWORK_BENCH", "--record or --replay, not both")
    tapes = [t.strip() for t in args.tapes.split(",") if t.strip()]
    missing = [t for t in tapes if not Path(t).is_file()]
    if not tapes or missing:
        raise InvariantError("REWORK_BENCH", f"--tapes names no tape it can read: {missing or 'none given'}")
    reworks = [r for t in tapes for r in reworks_from(Path(t))]
    if not reworks:
        raise InvariantError("REWORK_BENCH", "those tapes hold no rework after a verifier's reply")
    trials = len(reworks) * len(arms) * args.repeat
    out = _out_path(args.out, Path(f"data/compare/reworks-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    config = {
        "adapter": "replay" if args.replay else args.adapter, "arms": list(arms), "tapes": [Path(t).name for t in tapes],
        "reworks": len(reworks), "was_right": sum(r.right_before for r in reworks), "repeat": args.repeat, "trials": trials,
    }
    if args.price_in is not None:
        config |= {"price_in": args.price_in, "price_out": args.price_out}
    if args.max_spend is not None:
        config["max_spend"] = args.max_spend
    if args.dry_run:
        print(json.dumps(config, indent=2))
        return 0
    factory, player, recorder = _model_source(args, config, "rework_bench", "REWORK_BENCH", ("arms", "tapes", "repeat"))
    try:
        results = run_bench(reworks, factory, arms=arms, repeats=args.repeat, workers=args.workers, progress=stderr,
                            stop_when=spend_cap(args.max_spend, args.price_in, args.price_out) if args.max_spend is not None else None)
    finally:
        if recorder:
            recorder.close()
    if len(results) < trials:
        config["stopped_after"] = len(results)
    summary = summarize(results, price_in=args.price_in, price_out=args.price_out)
    save(out, config=config, results=results, summary=summary)
    print(render(summary))
    if player:
        print(f"replay: {player.served} replies served ({player.repeated} repeated), "
              f"{player.misses} requests the tape does not have")
    if recorder:
        print(f"tape: {recorder.count} exchanges saved to {args.record}")
    print(f"saved {out}")
    return 0


def cmd_plan_bench(args: argparse.Namespace) -> int:
    import time

    from .compare import comparison_budget, spend_cap, stderr
    from .plan_bench import ENTITIES, render, run_bench, save, summarize
    from .suite import build_suite

    shapes = tuple(dict.fromkeys(s.strip() for s in args.shapes.split(",") if s.strip()))
    bad = set(shapes) - set(PLAN_SHAPES)
    if not shapes or bad:
        raise InvariantError("PLAN_BENCH", f"name shapes from {list(PLAN_SHAPES)}" + (f"; unknown: {sorted(bad)}" if bad else ""))
    if (args.price_in is None) != (args.price_out is None):
        raise InvariantError("PLAN_BENCH", "give both --price-in and --price-out, or neither")
    if args.max_spend is not None and args.price_in is None:
        raise InvariantError("PLAN_BENCH", "--max-spend needs --price-in and --price-out")
    if args.record and args.replay:
        raise InvariantError("PLAN_BENCH", "--record or --replay, not both")
    try:
        suite = build_suite(seed=args.seed, per_family=args.questions, families=("aggregate", "breadth"),
                            entities=ENTITIES, distractors=args.distractors)
    except ValueError as e:
        raise InvariantError("PLAN_BENCH", str(e)) from None
    plans = len(suite.tasks) * len(shapes) * args.repeat
    out = _out_path(args.out, Path(f"data/compare/plan-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    config = {
        "adapter": "replay" if args.replay else args.adapter, "shapes": list(shapes), "questions": args.questions,
        "entities": ENTITIES, "distractors": args.distractors, "repeat": args.repeat, "seed": args.seed,
        "max_calls_per_trial": args.max_calls, "context_tokens": args.context, "tool_rounds": args.tool_rounds, "plans": plans,
    }
    if args.price_in is not None:
        config |= {"price_in": args.price_in, "price_out": args.price_out}
    if args.max_spend is not None:
        config["max_spend"] = args.max_spend
    if args.dry_run:
        print(json.dumps(config, indent=2))
        return 0
    factory, player, recorder = _model_source(
        args, config, "plan_bench", "PLAN_BENCH",
        ("shapes", "questions", "entities", "distractors", "repeat", "seed", "max_calls_per_trial", "context_tokens", "tool_rounds"),
    )
    if args.corpus:
        suite.write_corpus(args.corpus)
    try:
        results = run_bench(
            suite, factory, shapes=shapes, repeats=args.repeat,
            budget_factory=lambda: comparison_budget(args.max_calls, args.context), tool_rounds=args.tool_rounds,
            corpus_dir=Path(args.corpus) if args.corpus else None, progress=stderr,
            stop_when=spend_cap(args.max_spend, args.price_in, args.price_out) if args.max_spend is not None else None,
        )
    finally:
        if recorder:
            recorder.close()
    if len(results) < plans:
        config["stopped_after"] = len(results)
    summary = summarize(results, price_in=args.price_in, price_out=args.price_out)
    save(out, config=config, results=results, summary=summary)
    print(render(summary))
    if player:
        print(f"replay: {player.served} replies served ({player.repeated} repeated), "
              f"{player.misses} requests the tape does not have")
    if recorder:
        print(f"tape: {recorder.count} exchanges saved to {args.record}")
    print(f"saved {out}")
    return 0


def cmd_report_bench(args: argparse.Namespace) -> int:
    import time

    from .compare import comparison_budget, spend_cap, stderr
    from .report_bench import parts, render, run_bench, save, summarize
    from .suite import build_suite

    setups = tuple(dict.fromkeys(s.strip() for s in args.setups.split(",") if s.strip()))
    bad = set(setups) - set(REPORT_SETUPS)
    if not setups or bad:
        raise InvariantError("REPORT_BENCH", f"name setups from {list(REPORT_SETUPS)}" + (f"; unknown: {sorted(bad)}" if bad else ""))
    if (args.price_in is None) != (args.price_out is None):
        raise InvariantError("REPORT_BENCH", "give both --price-in and --price-out, or neither")
    if args.max_spend is not None and args.price_in is None:
        raise InvariantError("REPORT_BENCH", "--max-spend needs --price-in and --price-out")
    if args.record and args.replay:
        raise InvariantError("REPORT_BENCH", "--record or --replay, not both")
    try:
        suite = build_suite(seed=args.seed, per_family=args.questions, families=("aggregate",),
                            entities=args.entities, distractors=args.distractors)
    except ValueError as e:
        raise InvariantError("REPORT_BENCH", str(e)) from None
    items = parts(suite)
    runs = len(items) * len(setups) * args.repeat
    out = _out_path(args.out, Path(f"data/compare/report-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    config = {
        "adapter": "replay" if args.replay else args.adapter, "setups": list(setups), "questions": args.questions,
        "entities": args.entities, "distractors": args.distractors, "repeat": args.repeat, "seed": args.seed,
        "max_calls_per_part": args.max_calls, "context_tokens": args.context,
        "parts": len(items), "wrong_parts": sum(p.kind != "right" for _, _, p in items), "runs": runs,
    }
    if args.price_in is not None:
        config |= {"price_in": args.price_in, "price_out": args.price_out}
    if args.max_spend is not None:
        config["max_spend"] = args.max_spend
    if args.dry_run:
        print(json.dumps(config, indent=2))
        return 0
    factory, player, recorder = _model_source(
        args, config, "report_bench", "REPORT_BENCH",
        ("setups", "questions", "entities", "distractors", "repeat", "seed", "max_calls_per_part", "context_tokens"),
    )
    if args.corpus:
        suite.write_corpus(args.corpus)
    try:
        results = run_bench(
            suite, factory, setups=setups, repeats=args.repeat,
            budget_factory=lambda: comparison_budget(args.max_calls, args.context),
            corpus_dir=Path(args.corpus) if args.corpus else None, progress=stderr,
            stop_when=spend_cap(args.max_spend, args.price_in, args.price_out) if args.max_spend is not None else None,
        )
    finally:
        if recorder:
            recorder.close()
    if len(results) < runs:
        config["stopped_after"] = len(results)
    summary = summarize(results, price_in=args.price_in, price_out=args.price_out)
    save(out, config=config, results=results, summary=summary)
    print(render(summary))
    if player:
        print(f"replay: {player.served} replies served ({player.repeated} repeated), "
              f"{player.misses} requests the tape does not have")
    if recorder:
        print(f"tape: {recorder.count} exchanges saved to {args.record}")
    print(f"saved {out}")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    from .bench import run_bench

    report = run_bench(Path(args.fixtures) if args.fixtures else None)
    print(json.dumps(report, indent=2))
    print(f"\n{report['passed']} passed, {report['failed']} failed")
    return 0 if report["failed"] == 0 else 1


def cmd_diagnose(args: argparse.Namespace) -> int:
    from .diagnostics import diagnose

    m = load_run(Path(args.path))
    print(json.dumps(diagnose(m), indent=2))
    return 0


def cmd_board(args: argparse.Namespace) -> int:
    from .diagnostics import diagnose
    from .schema import state_contract

    m = load_run(Path(args.path))
    report = diagnose(m)
    print(json.dumps({
        "id": m.id,
        "status": m.status.value,
        "roster": [s.id for s in m.state.slots],
        "workers": m.state.worker_count(),
        "state": state_contract(m.state),
        "open_reviews": m.open_review_ids(),
        "streams": report["streams"],
        "tier": report.get("tier", {}),
        "health": report["health"],
        "verify": getattr(m, "last_verify", None),
        "stop_reason": getattr(m, "stop_reason", ""),
    }, indent=2))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    m = load_run(Path(args.path))
    tail = [{"event": e.event, "detail": e.detail} for e in m.log[-8:]]
    print(json.dumps({"state": {
        "goal": m.state.goal,
        "purpose": m.state.purpose,
        "context": m.state.context,
        "method": m.state.method,
        "initial_context": m.state.initial_context,
        "axes": m.state.axes,
    }, "summary": m.summary(), "tail": tail}, indent=2))
    return 0


def cmd_policy_replay(args: argparse.Namespace) -> int:
    from .policy import replay_path

    pairs = replay_path(args.path)
    print(json.dumps({"path": args.path, "n": len(pairs), "pairs": pairs}, indent=2))
    return 0


def cmd_policy_rl(args: argparse.Namespace) -> int:
    from .rl import compare_to_stub

    print(json.dumps(compare_to_stub(args.episodes), indent=2))
    return 0


def cmd_policy_sft(args: argparse.Namespace) -> int:
    from .finetune import build_corpus, write_jsonl

    rows = build_corpus(args.n)
    saved = str(write_jsonl(Path(args.out), rows))
    labels = {}
    for row in rows:
        labels[row["label"]] = labels.get(row["label"], 0) + 1
    print(json.dumps({"ok": True, "saved": saved, "n": len(rows), "labels": labels}, indent=2))
    return 0


def cmd_policy_finetune(args: argparse.Namespace) -> int:
    from .finetune import build_corpus, fine_tune_head
    from .imitate import dump, synthesize, confusion
    from .rl import evaluate

    rows = build_corpus(240)
    pol = fine_tune_head(rows)
    saved = str(dump(pol.head, Path(args.out)))
    report = confusion(synthesize(80), pol)
    print(json.dumps({"ok": True, "saved": saved, "heldout": report, "rl": evaluate(pol)}, indent=2))
    return 0


def cmd_policy_fit(args: argparse.Namespace) -> int:
    from .imitate import ImitationPolicy, confusion, dump, synthesize, vs_stub

    rows = synthesize(180)
    pol = ImitationPolicy.train_default()
    report = confusion(rows, pol)
    stub = vs_stub(rows)
    saved = str(dump(pol.head, Path(args.out)))
    print(json.dumps({"ok": True, "saved": saved, "imitation": report, "stub": stub}, indent=2))
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    m = load_run(Path(args.path))
    print(json.dumps({"summary": m.summary(), "log": [{"event": e.event, "detail": e.detail} for e in m.log]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
