"""Genet-native bench. Score the graph, not the essay.

Each fixture in fixtures/bench/*.json names a mode, a pace, the operator's
inputs, and an expect block. The runner drives the engine with the stub
adapter and compares the board to expect, key by key.

modes      standing | adapt | split | mission | refuse_someone_else
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
from .factory import element_at_rest
from .gates import Seam, World, assess
from .loop import Engine
from .memory_store import MemoryStore
from .models import Slot
from .seams import parse_seams

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "bench"


def _seams(spec: dict) -> list[Seam]:
    if spec.get("seams"):
        return [Seam(a, b) for a, b in spec["seams"]]
    return parse_seams(spec.get("look", ""))


def _drive(spec: dict, store: MemoryStore):
    """Run one fixture. Returns (mission, error code or "")."""
    budget = Budget.for_pace(spec.get("pace", "crawl"))
    if spec.get("max_calls") is not None:
        budget.max_calls = int(spec["max_calls"])
    m = element_at_rest(spec["id"], spec["effect"], spec["purpose"], spec["end_state"])
    m.world = World(existing_files=list(spec.get("exists", [])), existing_channels=[Path(p).stem for p in spec.get("exists", [])])
    engine = Engine(store, budget=budget)
    mode = spec.get("mode", "standing")
    look = spec.get("look", "")
    try:
        if mode == "standing":
            engine.run_standing_order(m, look_update=look, operator_why="Could this have been one body?")
        elif mode == "adapt":
            engine.adapt_vector(m, look_update=look, report=spec["report"], new_method=spec["method"], axes=spec.get("axes", ["reroute"]))
        elif mode == "split":
            engine.run_multi_axis(m, look_update=look, seams=_seams(spec), axes=spec.get("axes", ["parallel", "fan_in"]), operator_why="Why split?")
        elif mode == "mission":
            engine.run_mission(m, look_update=look)
        elif mode == "refuse_someone_else":
            # The world already covers the work: the gates refuse, and forcing the
            # refused record through write_who fails at gate one.
            engine._arm(m)
            verdict = assess(_seams(spec), world=m.world)[0]
            worker = Slot(id=f"w-{verdict.seam.channel_id}", function="worker", channel_id=verdict.seam.channel_id)
            m.write_who(m.picture.who_head_id, m.picture.slots + [worker], gates=verdict.gates)
        else:
            raise ValueError(f"unknown bench mode: {mode}")
    except InvariantError as e:
        return m, e.code
    return m, ""


def run_fixture(spec: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        m, code = _drive(spec, MemoryStore(Path(tmp)))
    report = diagnose(m)
    answer = m.notes["why-1"].reason if "why-1" in m.notes else ""
    got = {
        "status": m.status.value,
        "code": code,
        "workers": m.picture.worker_count(),
        "split": any(e.event == "split" for e in m.log),
        "health": report["health"],
        "method_contains": m.picture.method,
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
    return {"id": spec["id"], "mode": spec.get("mode"), "pace": spec.get("pace"), "ok": all(c["ok"] for c in checks), "checks": checks}


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
