from __future__ import annotations

import argparse
import json
from pathlib import Path

from .budget import Budget
from .errors import InvariantError
from .factory import element_at_rest
from .gates import Seam, World
from .live import pick_adapter
from .loop import Engine
from .memory_store import MemoryStore
from .persist import load_mission, save_mission
from .reads import attach_reads
from .seams import parse_seams
from .tools import Toolbox


DEFAULT_DOCTRINE = """# Genet doctrine (v1)

- Structure lives in code. Prompts describe work, not authority.
- Only the lead may change the roster.
- Context decides which skill is active. The goal stays fixed until revised.
- Inspect context → activate a skill → gates → maybe add a worker.
- The reviewer is heard and answered. The reviewer does not take over the roster.
- Could-we is the last gate, not the first.
"""


def _store(root) -> MemoryStore:
    """Plain file store. Doctrine is seeded once; an operator's edits are kept."""
    store = MemoryStore(Path(root))
    if not store.read_doctrine("standing"):
        store.write_doctrine("standing", DEFAULT_DOCTRINE)
    return store


def _add_budget_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--pace", default="crawl", choices=["crawl", "walk", "run"])
    p.add_argument("--max-calls", type=int, default=None)
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--max-seconds", type=float, default=None)
    p.add_argument("--max-tokens-per-call", type=int, default=None)


def _add_mission_args(p: argparse.ArgumentParser, *, required: tuple[str, ...] = (), **defaults: str) -> None:
    """Flags every mission command shares. defaults maps flag name (underscored) to default."""
    for flag in ("id", "effect", "purpose", "end_state", "look"):
        name = "--" + flag.replace("_", "-")
        if flag in required:
            p.add_argument(name, required=True)
        else:
            p.add_argument(name, default=defaults[flag])
    p.add_argument("--store", default="data")
    p.add_argument("--out", default=defaults["out"])
    p.add_argument("--adapter", default="stub", choices=["stub", "live"])
    p.add_argument("--read", action="append", default=[], help="file text into working memory; not a new Worker")
    p.add_argument("--criteria", action="append", default=[], help="success criterion the product must show")
    p.add_argument("--exists", action="append", default=[], help="file already on disk; its name covers a channel")
    p.add_argument("--workspace", action="append", default=[], help="directory specialists may read and search")
    _add_budget_args(p)


def _budget(args: argparse.Namespace) -> Budget:
    b = Budget.for_pace(getattr(args, "pace", "crawl"))
    if args.max_calls is not None:
        b.max_calls = args.max_calls
    if args.max_tokens is not None:
        b.max_tokens = args.max_tokens
    if args.max_seconds is not None:
        b.max_seconds = args.max_seconds
    if args.max_tokens_per_call is not None:
        b.max_tokens_per_call = args.max_tokens_per_call
    return b


def _new_mission(args: argparse.Namespace, store: MemoryStore):
    """Fresh mission: clean working memory, then operator reads, criteria, and world."""
    mission = element_at_rest(args.id, args.effect, args.purpose, args.end_state)
    store.reset_working(mission.id)
    attach_reads(store, mission, args.read)
    if args.criteria:
        mission.picture.success_criteria = list(args.criteria)
    exists = [str(p) for p in args.exists]
    mission.world = World(existing_files=exists, existing_channels=[Path(p).stem for p in exists])
    return mission


def _engine(args: argparse.Namespace, store: MemoryStore) -> Engine:
    for root in args.workspace:
        if not Path(root).is_dir():
            raise InvariantError("READ", f"workspace is not a directory: {root}")
    toolbox = Toolbox(roots=args.workspace, files=args.read)
    return Engine(store, adapter=pick_adapter(args.adapter), budget=_budget(args), toolbox=toolbox)


def _axes(raw: str) -> list[str]:
    return [a.strip() for a in raw.split(",") if a.strip()]


def _save_halt(mission, out: Path, err: InvariantError) -> int:
    out = Path(out)
    try:
        save_mission(mission, out)
        saved = str(out)
    except Exception:
        saved = None
    print(json.dumps({
        "ok": False,
        "halt": True,
        "code": err.code,
        "error": str(err),
        "status": getattr(mission, "status", None) and mission.status.value,
        "stop_reason": getattr(mission, "stop_reason", ""),
        "saved": saved,
    }, indent=2))
    if saved:
        print(f"\nsaved {out}")
    return 1


def _save_done(result, out: Path, **extra) -> int:
    out = Path(out)
    save_mission(result.mission, out)
    print(json.dumps(result.mission.summary() | {"product": result.product.claim} | extra, indent=2))
    print(f"\nsaved {out}")
    return 0


def cmd_mission(args: argparse.Namespace) -> int:
    store = _store(args.store)
    mission = _new_mission(args, store)
    try:
        result = _engine(args, store).run_mission(mission, look_update=args.look, operator_why=args.why)
    except InvariantError as e:
        return _save_halt(mission, args.out, e)
    gates = [
        {"channel": v.seam.channel_id, "skill": v.seam.skill, "legal": v.legal, "refused": v.refused}
        for v in result.verdicts or []
    ]
    return _save_done(result, args.out, gates=gates, answer=mission.notes["why-1"].reason)


def cmd_run(args: argparse.Namespace) -> int:
    store = _store(args.store)
    mission = _new_mission(args, store)
    try:
        result = _engine(args, store).run_standing_order(
            mission,
            look_update=args.look,
            operator_why=args.why,
            head_response=args.response,
            head_reason=args.reason,
        )
    except InvariantError as e:
        return _save_halt(mission, args.out, e)
    return _save_done(result, args.out)


def cmd_split(args: argparse.Namespace) -> int:
    store = _store(args.store)
    mission = _new_mission(args, store)
    seams = parse_seams(args.look)
    if not seams:
        for part in args.seams.split(","):
            if ":" not in part:
                continue
            head, failure = part.split(":", 1)
            channel, _, skill = head.partition("@")
            seams.append(Seam(channel.strip(), failure.strip(), skill=skill.strip().lower() or "execute"))
    try:
        result = _engine(args, store).run_multi_axis(
            mission,
            look_update=args.look,
            seams=seams,
            axes=_axes(args.axes),
            operator_why=args.why,
            head_response=args.response,
            head_reason=args.reason,
        )
    except InvariantError as e:
        return _save_halt(mission, args.out, e)
    return _save_done(result, args.out, split=result.split)


def cmd_adapt(args: argparse.Namespace) -> int:
    store = _store(args.store)
    mission = _new_mission(args, store)
    try:
        result = _engine(args, store).adapt_vector(
            mission,
            look_update=args.look,
            report=args.report,
            new_method=args.method,
            axes=_axes(args.axes),
        )
    except InvariantError as e:
        return _save_halt(mission, args.out, e)
    return _save_done(result, args.out)


def cmd_brief(args: argparse.Namespace) -> int:
    from .diagnostics import diagnose
    from .schema import picture_contract

    store = _store(args.store)
    mission = _new_mission(args, store)
    try:
        result = _engine(args, store).run_standing_order(
            mission,
            look_update=args.look,
            operator_why=args.why,
        )
    except InvariantError as e:
        return _save_halt(mission, args.out, e)
    save_mission(result.mission, Path(args.out))
    report = diagnose(result.mission)
    print(json.dumps({
        "ok": True,
        "picture": picture_contract(result.mission.picture),
        "product": result.product.claim if result.product else None,
        "could_this_have_been_one": result.mission.picture.worker_count() == 0,
        "health": report["health"],
        "pace": report["pace"]["name"],
        "saved": str(args.out),
    }, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="taskorg", description="Genet — small multi-agent runtime")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mission", help="the lead reads the look and organizes the team; gates judge it")
    _add_mission_args(
        m,
        id="ms-001",
        effect="Complete the task",
        purpose="Keep the goal intact",
        end_state="Task finished",
        look="One source is the whole picture.",
        out="data/missions/ms-001.json",
    )
    m.add_argument("--why", default="Could this have been one body?")
    m.set_defaults(func=cmd_mission)

    r = sub.add_parser("run", help="one body: look, draft, verify")
    _add_mission_args(
        r,
        id="so-001",
        effect="Complete the default task",
        purpose="Keep one shared context and one plan",
        end_state="Task recorded and review closed",
        look="Primary path blocked. Two independent sources are visible.",
        out="data/missions/so-001.json",
    )
    r.add_argument("--why", default="Why solve this with one worker instead of splitting sources?")
    r.add_argument("--response", default="KEEP_ROSTER")
    r.add_argument("--reason", default="Context is enough; no second worker required.")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("split", help="look, then gated multi-axis split on named seams")
    _add_mission_args(
        s,
        id="mx-001",
        effect="Complete the task",
        purpose="Keep the goal intact",
        end_state="Task finished",
        look="Primary path blocked. source-a and source-b are independent.",
        out="data/missions/mx-001.json",
    )
    s.add_argument("--seams", default="source-a:independent source-a channel,source-b:independent source-b channel",
                   help="channel[@qual]:named failure, comma separated; used when --look tags no seams")
    s.add_argument("--axes", default="parallel,fan_in")
    s.add_argument("--why", default="Why keep one worker if two sources are independent?")
    s.add_argument("--response", default="CHANGE_METHOD")
    s.add_argument("--reason", default="Sources are independent. Method can fan out. Roster stays small.")
    s.set_defaults(func=cmd_split)

    a = sub.add_parser("adapt", help="plan is wrong: report up and change the method")
    _add_mission_args(
        a,
        id="pw-001",
        effect="Complete the task",
        purpose="Keep the goal intact",
        end_state="Task finished",
        look="First source is a decoy. Second source is the real line.",
        out="data/missions/pw-001.json",
    )
    a.add_argument("--report", default="First plan is dead — first source is a decoy")
    a.add_argument("--method", default="circumvent via source-b")
    a.add_argument("--axes", default="reroute")
    a.set_defaults(func=cmd_adapt)

    p_b = sub.add_parser("brief", help="operator loop: effect + purpose + look → picture, How, diagnose")
    _add_mission_args(
        p_b,
        required=("effect", "purpose", "look"),
        id="brief-001",
        end_state="Intent held",
        out="data/missions/brief-001.json",
    )
    p_b.add_argument("--why", default="Could this have been one body?")
    p_b.set_defaults(func=cmd_brief)

    p_replay = sub.add_parser("replay", help="print a saved mission log")
    p_replay.add_argument("path")
    p_replay.set_defaults(func=cmd_replay)

    p_ins = sub.add_parser("inspect", help="short picture + last log events")
    p_ins.add_argument("path")
    p_ins.set_defaults(func=cmd_inspect)

    p_board = sub.add_parser("board", help="one-screen operator picture")
    p_board.add_argument("path")
    p_board.set_defaults(func=cmd_board)

    p_bench = sub.add_parser("bench", help="score the fixtures in fixtures/bench against their expect blocks")
    p_bench.add_argument("--fixtures", default=None, help="directory of bench fixtures (default: the repo's)")
    p_bench.set_defaults(func=cmd_bench)

    p_c = sub.add_parser("compare", help="single agent vs always-split crew vs genet on the synthetic suite")
    p_c.add_argument("--adapter", default="stub", choices=["stub", "sim", "live"],
                     help="stub: plumbing only; sim: deterministic reader, structural cost at $0; live: a real model")
    p_c.add_argument("--strategies", default="single,always,genet")
    p_c.add_argument("--families", default="lookup,aggregate,compare,breadth")
    p_c.add_argument("--per-family", type=int, default=5)
    p_c.add_argument("--repeat", type=int, default=1)
    p_c.add_argument("--seed", type=int, default=7)
    p_c.add_argument("--max-calls", type=int, default=40, help="per-trial call cap, same for every strategy")
    p_c.add_argument("--context", type=int, default=16_000, help="per-call token cap, same for every strategy")
    p_c.add_argument("--tool-rounds", type=int, default=3)
    p_c.add_argument("--price-in", type=float, default=None, help="$ per 1M input tokens, for cost columns")
    p_c.add_argument("--price-out", type=float, default=None, help="$ per 1M output tokens")
    p_c.add_argument("--corpus", default=None, help="also write the corpus here, to read it")
    p_c.add_argument("--out", default=None, help="results JSON (default data/compare/compare-<time>.json)")
    p_c.add_argument("--dry-run", action="store_true", help="print the plan and call ceiling; call no model")
    p_c.set_defaults(func=cmd_compare)

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
    p_rl.add_argument("--episodes", type=int, default=60)
    p_rl.set_defaults(func=cmd_policy_rl)
    p_sft = sub.add_parser("policy-sft", help="write chat JSONL for a later model trainer")
    p_sft.add_argument("--out", default="data/policy/sft.jsonl")
    p_sft.add_argument("--n", type=int, default=240)
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


def cmd_compare(args: argparse.Namespace) -> int:
    import time

    from .compare import STRATEGIES, comparison_budget, render, run_comparison, save, stderr, summarize
    from .suite import FAMILIES, build_suite

    strategies = tuple(s.strip() for s in args.strategies.split(",") if s.strip())
    families = tuple(f.strip() for f in args.families.split(",") if f.strip())
    bad = (set(strategies) - set(STRATEGIES)) | (set(families) - set(FAMILIES))
    if bad:
        raise InvariantError("COMPARE", f"unknown strategy or family: {sorted(bad)}")
    if (args.price_in is None) != (args.price_out is None):
        raise InvariantError("COMPARE", "give both --price-in and --price-out, or neither")
    suite = build_suite(seed=args.seed, per_family=args.per_family, families=families)
    trials = len(suite.tasks) * len(strategies) * args.repeat
    config = {
        "adapter": args.adapter, "strategies": list(strategies), "families": list(families),
        "per_family": args.per_family, "repeat": args.repeat, "seed": args.seed,
        "max_calls_per_trial": args.max_calls, "context_tokens": args.context, "tool_rounds": args.tool_rounds,
        "trials": trials, "call_ceiling": trials * args.max_calls,
    }
    if args.dry_run:
        print(json.dumps(config | {"tasks": [t.question for t in suite.tasks]}, indent=2))
        return 0
    pick_adapter(args.adapter)  # fail fast on missing live configuration
    if args.corpus:
        suite.write_corpus(args.corpus)
    results = run_comparison(
        suite,
        lambda: pick_adapter(args.adapter),
        strategies=strategies,
        repeats=args.repeat,
        budget_factory=lambda: comparison_budget(args.max_calls, args.context),
        tool_rounds=args.tool_rounds,
        corpus_dir=Path(args.corpus) if args.corpus else None,
        progress=stderr,
    )
    summary = summarize(results, price_in=args.price_in, price_out=args.price_out)
    out = Path(args.out or f"data/compare/compare-{time.strftime('%Y%m%d-%H%M%S')}.json")
    save(out, config=config, results=results, summary=summary)
    print(render(summary))
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

    m = load_mission(Path(args.path))
    print(json.dumps(diagnose(m), indent=2))
    return 0


def cmd_board(args: argparse.Namespace) -> int:
    from .diagnostics import diagnose
    from .schema import picture_contract

    m = load_mission(Path(args.path))
    report = diagnose(m)
    print(json.dumps({
        "id": m.id,
        "status": m.status.value,
        "who": [s.id for s in m.picture.slots],
        "workers": m.picture.worker_count(),
        "picture": picture_contract(m.picture),
        "open_why": m.open_why_ids(),
        "nets": report["nets"],
        "pace": report.get("pace", {}),
        "health": report["health"],
        "verify": getattr(m, "last_verify", None),
        "stop_reason": getattr(m, "stop_reason", ""),
    }, indent=2))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    m = load_mission(Path(args.path))
    tail = [{"event": e.event, "detail": e.detail} for e in m.log[-8:]]
    print(json.dumps({"picture": {
        "what": m.picture.effect,
        "why": m.picture.purpose,
        "where": m.picture.current_picture,
        "how": m.picture.method,
        "step_off": m.picture.step_off_picture,
        "axes": m.picture.axes,
    }, "summary": m.summary(), "tail": tail}, indent=2))
    return 0


def cmd_policy_replay(args: argparse.Namespace) -> int:
    from .policy import replay_path

    pairs = replay_path(args.path)
    print(json.dumps({"path": args.path, "n": len(pairs), "pairs": pairs}, indent=2))
    return 0


def cmd_policy_rl(args: argparse.Namespace) -> int:
    from .rl import compare_to_stub, train

    _pol, _ = train(args.episodes)
    print(json.dumps(compare_to_stub(), indent=2))
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
    m = load_mission(Path(args.path))
    print(json.dumps({"summary": m.summary(), "log": [{"event": e.event, "detail": e.detail} for e in m.log]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
