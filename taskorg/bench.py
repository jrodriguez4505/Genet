"""Genet-native bench. Score the graph, not the essay.

Each fixture in fixtures/bench/*.json names a mode, a budget tier, the operator's
inputs, and an expect block. The runner drives the engine with the stub
adapter and compares the board to expect, key by key.

modes      single | replan | fanout | run | refuse_someone_else
expect     status, code, workers, split, health, method_contains,
           isolation_flags_empty, refused_contains, calls_max
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .budget import Budget
from .diagnostics import diagnose
from .errors import InvariantError
from .factory import new_run
from .gates import Subtask, World, assess
from .loop import Engine
from .memory_store import MemoryStore
from .models import Slot
from .subtasks import parse_subtasks

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "bench"


def _subtasks(spec: dict) -> list[Subtask]:
    if spec.get("subtasks"):
        return [Subtask(a, b) for a, b in spec["subtasks"]]
    return parse_subtasks(spec.get("context", ""))


def _drive(spec: dict, store: MemoryStore):
    """Run one fixture. Returns (run, error code or "")."""
    budget = Budget.for_tier(spec.get("tier", "tight"))
    if spec.get("max_calls") is not None:
        budget.max_calls = int(spec["max_calls"])
    m = new_run(spec["id"], spec["goal"], spec["purpose"], spec["done_when"])
    m.world = World(existing_files=list(spec.get("exists", [])), existing_channels=[Path(p).stem for p in spec.get("exists", [])])
    engine = Engine(store, budget=budget)
    mode = spec.get("mode", "single")
    context = spec.get("context", "")
    try:
        if mode == "single":
            engine.run_single(m, context=context, operator_question="Could a single agent have done this?")
        elif mode == "replan":
            engine.run_replan(m, context=context, replan_reason=spec["replan_reason"], new_method=spec["method"], axes=spec.get("axes", ["reroute"]))
        elif mode == "fanout":
            engine.run_fanout(m, context=context, subtasks=_subtasks(spec), axes=spec.get("axes", ["parallel", "fan_in"]), operator_question="Why split?")
        elif mode == "run":
            engine.run_task(m, context=context)
        elif mode == "refuse_someone_else":
            # The world already covers the work: the gates refuse, and forcing the
            # refused record through set_roster fails at gate one.
            engine._arm(m)
            verdict = assess(_subtasks(spec), world=m.world)[0]
            worker = Slot(id=f"w-{verdict.subtask.channel_id}", function="worker", channel_id=verdict.subtask.channel_id)
            m.set_roster(m.state.lead_id, m.state.slots + [worker], gates=verdict.gates)
        else:
            raise ValueError(f"unknown bench mode: {mode}")
    except InvariantError as e:
        return m, e.code
    return m, ""


def run_fixture(spec: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        m, code = _drive(spec, MemoryStore(Path(tmp)))
    report = diagnose(m)
    answer = m.notes["question-1"].reason if "question-1" in m.notes else ""
    got = {
        "status": m.status.value,
        "code": code,
        "workers": m.state.worker_count(),
        "split": any(e.event == "split" for e in m.log),
        "health": report["health"],
        "method_contains": m.state.method,
        "isolation_flags_empty": not report["isolation"]["flags"],
        "refused_contains": answer,
        "calls_max": len(m.calls),
    }
    checks = []
    for key, want in (spec.get("expect") or {}).items():
        have = got.get(key)
        if key in ("method_contains", "refused_contains"):
            ok = str(want) in str(have)
        elif key == "calls_max":
            ok = have <= want
        else:
            ok = have == want
        checks.append({"key": key, "want": want, "got": have, "ok": ok})
    return {"id": spec["id"], "mode": spec.get("mode"), "tier": spec.get("tier"), "ok": all(c["ok"] for c in checks), "checks": checks}


def run_bench(fixtures: Path | None = None) -> dict:
    root = Path(fixtures) if fixtures else DEFAULT_DIR
    if not root.is_dir():
        raise InvariantError("READ", f"no bench fixtures at {root}; pass --fixtures")
    results = [run_fixture(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(root.glob("*.json"))]
    return {
        "fixtures": str(root),
        "passed": sum(r["ok"] for r in results),
        "failed": sum(not r["ok"] for r in results),
        "results": results,
    }
