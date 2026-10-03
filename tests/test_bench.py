"""Genet-native bench. Score the graph, not the essay."""

import json
from pathlib import Path

import pytest

from taskorg.budget import Budget
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.gates import Subtask, World, decide
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import GateRecord, GATE_ORDER, Slot

BENCH = Path(__file__).resolve().parents[1] / "fixtures" / "bench"


def _load(name: str) -> dict:
    return json.loads((BENCH / name).read_text())


def _engine(tmp_path: Path, spec: dict) -> Engine:
    b = Budget.for_tier(spec.get("tier", "tight"))
    if spec.get("max_calls") is not None:
        b.max_calls = int(spec["max_calls"])
    return Engine(MemoryStore(tmp_path), budget=b)


def test_single_agent(tmp_path: Path):
    spec = _load("single_agent.json")
    m = new_run(spec["id"], spec["goal"], spec["purpose"], spec["done_when"])
    result = _engine(tmp_path, spec).run_single(
        m, context=spec["context"], operator_question="one agent?"
    )
    assert result.run.status.value == spec["expect"]["status"]
    assert result.run.state.worker_count() == 0
    assert result.split is False
    assert diagnose(m)["health"] == "ok"


def test_replan(tmp_path: Path):
    spec = _load("replan.json")
    m = new_run(spec["id"], spec["goal"], spec["purpose"], spec["done_when"])
    result = _engine(tmp_path, spec).run_replan(
        m,
        context=spec["context"],
        replan_reason=spec["replan_reason"],
        new_method=spec["method"],
        axes=spec["axes"],
    )
    assert result.run.status.value == "complete"
    assert result.run.state.worker_count() == 0
    assert spec["expect"]["method_contains"] in result.run.state.method


def test_two_sources(tmp_path: Path):
    spec = _load("two_sources.json")
    m = new_run(spec["id"], spec["goal"], spec["purpose"], spec["done_when"])
    subtasks = [Subtask(a, b) for a, b in spec["subtasks"]]
    result = _engine(tmp_path, spec).run_fanout(
        m,
        context=spec["context"],
        subtasks=subtasks,
        axes=spec["axes"],
        operator_question="two notes?",
    )
    assert result.split is True
    assert result.run.state.worker_count() == 2
    iso = diagnose(m)["isolation"]
    assert iso["flags"] == []


def test_already_exists():
    spec = _load("already_exists.json")
    m = new_run(spec["id"], spec["goal"], spec["purpose"], spec["done_when"])
    world = World(existing_files=["out/summary.md"], existing_channels=["summary"])
    assert decide([Subtask("summary", "need a summary writer")], world=world) is None
    bad = GateRecord(
        can_someone_else=True,
        should_we=True,
        named_failure="file already on disk",
        could_we=True,
        channel_id="summary",
        order=GATE_ORDER,
    )
    with pytest.raises(InvariantError) as e:
        m.set_roster(
            "lead-1",
            m.state.slots + [Slot(id="w-summary", function="worker", channel_id="summary")],
            gates=bad,
        )
    assert e.value.code == spec["expect"]["code"]
    assert m.state.worker_count() == 0


def test_budget_cap(tmp_path: Path):
    spec = _load("budget_cap.json")
    m = new_run(spec["id"], spec["goal"], spec["purpose"], spec["done_when"])
    with pytest.raises(InvariantError) as e:
        _engine(tmp_path, spec).run_single(
            m, context=spec["context"], operator_question="stop?"
        )
    assert e.value.code == spec["expect"]["code"]
    assert m.status.value == spec["expect"]["status"]


def test_every_fixture_meets_its_expect_block():
    from taskorg.bench import run_bench

    report = run_bench(BENCH)
    failed = [(r["id"], [c for c in r["checks"] if not c["ok"]]) for r in report["results"] if not r["ok"]]
    assert not failed, failed
    assert report["passed"] == len(list(BENCH.glob("*.json")))
