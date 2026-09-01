from __future__ import annotations

import argparse
import json
from pathlib import Path

from .budget import Budget
from .errors import InvariantError
from .factory import element_at_rest
from .gates import Seam
from .seams import parse_seams
from .live import pick_adapter
from .loop import Engine
from .memory_store import MemoryStore
from .persist import load_mission, save_mission


DEFAULT_DOCTRINE = """# Genet doctrine (v1)

- Genet in this repo is the agent kernel, not the playwright Jean Genet.
- Structure lives in code. Prompts describe work, not authority.
- Only the lead may change the roster.
- Context decides which skill is active. The goal stays fixed until revised.
- Inspect context → activate a skill → gates → maybe add a worker.
- The reviewer is heard and answered. The reviewer does not take over the roster.
- Could-we is the last gate, not the first.
"""


def _add_budget_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--pace", default="crawl", choices=["crawl", "walk", "run"])
    p.add_argument("--max-calls", type=int, default=None)
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--max-seconds", type=float, default=None)
    p.add_argument("--max-tokens-per-call", type=int, default=None)


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


def cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.store)
    store = MemoryStore(root)
    store.write_doctrine("standing", DEFAULT_DOCTRINE)
    mission = element_at_rest(args.id, effect=args.effect, purpose=args.purpose, end_state=args.end_state)
    from .reads import attach_reads
    attach_reads(store, mission, getattr(args, "read", []) or [])
    if getattr(args, "criteria", None):
        mission.picture.success_criteria = list(args.criteria)
    engine = Engine(store, adapter=pick_adapter(args.adapter), budget=_budget(args))
    try:
        result = engine.run_standing_order(
            mission,
            look_update=args.look,
            operator_why=args.why,
            head_response=args.response,
            head_reason=args.reason,
        )
    except InvariantError as e:
        return _save_halt(mission, Path(args.out), e)
    out = Path(args.out)
    save_mission(result.mission, out)
    print(json.dumps(result.mission.summary() | {"product": result.product.claim}, indent=2))
    print(f"\nsaved {out}")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    import pytest
    root = Path(__file__).resolve().parents[1]
    rc = pytest.main(["-q", str(root / "tests" / "test_bench.py"), str(root / "tests" / "test_world.py")])
    return 0 if rc == 0 else 1


def cmd_split(args: argparse.Namespace) -> int:
    root = Path(args.store)
    store = MemoryStore(root)
    store.write_doctrine("standing", DEFAULT_DOCTRINE)
    mission = element_at_rest(args.id, args.effect, args.purpose, args.end_state)
    from .gates import World
    exists = [str(p) for p in getattr(args, "exists", []) or []]
    mission.world = World(existing_files=exists, existing_channels=[Path(p).stem for p in exists])
    from .reads import attach_reads
    attach_reads(store, mission, getattr(args, "read", []) or [])
    seams = parse_seams(args.look)
    if not seams:
        for part in args.seams.split(","):
            if ":" not in part:
                continue
            channel, failure = part.split(":", 1)
            seams.append(Seam(channel.strip(), failure.strip()))
    axes = [a.strip() for a in args.axes.split(",") if a.strip()]
    try:
        result = Engine(store, adapter=pick_adapter(args.adapter), budget=_budget(args)).run_multi_axis(
            mission,
            look_update=args.look,
            seams=seams,
            axes=axes,
            operator_why=args.why,
            head_response=args.response,
            head_reason=args.reason,
        )
    except InvariantError as e:
        return _save_halt(mission, Path(args.out), e)
    out = Path(args.out)
    save_mission(result.mission, out)
    print(json.dumps(result.mission.summary() | {"product": result.product.claim, "split": result.split}, indent=2))
    print(f"\nsaved {out}")
    return 0


def cmd_adapt(args: argparse.Namespace) -> int:
    store = MemoryStore(Path(args.store))
    store.write_doctrine("standing", DEFAULT_DOCTRINE)
    mission = element_at_rest(args.id, args.effect, args.purpose, args.end_state)
    axes = [x.strip() for x in args.axes.split(",") if x.strip()]
    try:
        result = Engine(store, adapter=pick_adapter(args.adapter), budget=_budget(args)).adapt_vector(
            mission,
            look_update=args.look,
            report=args.report,
            new_method=args.method,
            axes=axes,
        )
    except InvariantError as e:
        return _save_halt(mission, Path(args.out), e)
    out = Path(args.out)
    save_mission(result.mission, out)
    print(json.dumps(result.mission.summary() | {"product": result.product.claim}, indent=2))
    print(f"\nsaved {out}")
    return 0


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


def cmd_brief(args: argparse.Namespace) -> int:
    from .diagnostics import diagnose
    from .schema import picture_contract
    store = MemoryStore(Path(args.store))
    store.write_doctrine("standing", DEFAULT_DOCTRINE)
    mission = element_at_rest(args.id, args.effect, args.purpose, args.end_state)
    try:
        result = Engine(store, adapter=pick_adapter(args.adapter), budget=_budget(args)).run_standing_order(
            mission,
            look_update=args.look,
            operator_why=args.why,
        )
    except InvariantError as e:
        return _save_halt(mission, Path(args.out), e)
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


def cmd_replay(args: argparse.Namespace) -> int:
    m = load_mission(Path(args.path))
    print(json.dumps({"summary": m.summary(), "log": [{"event": e.event, "detail": e.detail} for e in m.log]}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="taskorg", description="Genet — default task loop")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a standing-order mission with the stub adapter")
    r.add_argument("--id", default="so-001")
    r.add_argument("--effect", default="Complete the default task")
    r.add_argument("--purpose", default="Keep one shared context and one plan")
    r.add_argument("--end-state", default="Task recorded and review closed")
    r.add_argument("--look", default="Primary path blocked. Two independent sources are visible.")
    r.add_argument("--why", default="Why solve this with one worker instead of splitting sources?")
    r.add_argument("--response", default="KEEP_ROSTER")
    r.add_argument("--reason", default="Context is enough; no second worker required.")
    r.add_argument("--store", default="data")
    r.add_argument("--out", default="data/missions/so-001.json")
    r.add_argument("--adapter", default="stub", choices=["stub", "live"])
    r.add_argument("--read", action="append", default=[], help="file text into the brief; one body")
    r.add_argument("--criteria", action="append", default=[], help="success criterion the Verifier must see")
    _add_budget_args(r)
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("split", help="look, then gated multi-axis split on named seams")
    s.add_argument("--id", default="mx-001")
    s.add_argument("--effect", default="Complete the task")
    s.add_argument("--purpose", default="Keep the goal intact")
    s.add_argument("--end-state", default="Task finished")
    s.add_argument("--look", default="Primary path blocked. source-a and source-b are independent.")
    s.add_argument("--seams", default="source-a:independent source-a channel,source-b:independent source-b channel")
    s.add_argument("--axes", default="parallel,sequential,fan_in")
    s.add_argument("--why", default="Why keep one worker if two sources are independent?")
    s.add_argument("--response", default="CHANGE_METHOD")
    s.add_argument("--reason", default="Sources are independent. Method can fan out. Roster stays small.")
    s.add_argument("--store", default="data")
    s.add_argument("--out", default="data/missions/mx-001.json")
    s.add_argument("--adapter", default="stub", choices=["stub", "live"])
    s.add_argument("--exists", action="append", default=[], help="file that already exists; decide() may refuse spawn")
    s.add_argument("--read", action="append", default=[], help="file text into the brief; not a new Worker")
    _add_budget_args(s)
    s.set_defaults(func=cmd_split)

    a = sub.add_parser("adapt", help="plan is wrong: report up and change the vector")
    a.add_argument("--id", default="pw-001")
    a.add_argument("--effect", default="Complete the task")
    a.add_argument("--purpose", default="Keep the goal intact")
    a.add_argument("--end-state", default="Task finished")
    a.add_argument("--look", default="First source is a decoy. Second source is the real line.")
    a.add_argument("--report", default="First plan is dead — first source is a decoy")
    a.add_argument("--method", default="use the second source")
    a.add_argument("--axes", default="reroute,sequential")
    a.add_argument("--store", default="data")
    a.add_argument("--out", default="data/missions/pw-001.json")
    a.add_argument("--adapter", default="stub", choices=["stub", "live"])
    _add_budget_args(a)
    a.set_defaults(func=cmd_adapt)

    p_replay = sub.add_parser("replay", help="print a saved mission log")
    p_replay.add_argument("path")
    p_replay.set_defaults(func=cmd_replay)

    p_ins = sub.add_parser("inspect", help="short picture + last log events")
    p_ins.add_argument("path")
    p_ins.set_defaults(func=cmd_inspect)

    p_b = sub.add_parser("brief", help="operator loop: effect + purpose + look")
    p_b.add_argument("--effect", required=True)
    p_b.add_argument("--purpose", required=True)
    p_b.add_argument("--look", required=True)
    p_b.add_argument("--end-state", default="Intent held")
    p_b.add_argument("--id", default="brief-001")
    p_b.add_argument("--why", default="Could this have been one body?")
    p_b.add_argument("--store", default="data")
    p_b.add_argument("--out", default="data/missions/brief-001.json")
    p_b.add_argument("--adapter", default="stub", choices=["stub", "live"])
    _add_budget_args(p_b)
    p_b.set_defaults(func=cmd_brief)

    p_board = sub.add_parser("board", help="one-screen operator picture")
    p_board.add_argument("path")
    p_board.set_defaults(func=cmd_board)
    p_bench = sub.add_parser("bench", help="run Genet-native fixtures")
    p_bench.set_defaults(func=cmd_bench)
    p_d = sub.add_parser("diagnose", help="performance and interaction at every level")
    p_d.add_argument("path")
    p_d.set_defaults(func=cmd_diagnose)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except InvariantError as e:
        print(json.dumps({"ok": False, "halt": True, "code": e.code, "error": str(e)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
