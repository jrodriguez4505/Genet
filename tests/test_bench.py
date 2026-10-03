"""Genet-native bench. Score the graph, not the essay."""

import json
from pathlib import Path

import pytest

from taskorg.budget import Budget
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.gates import Seam, World, decide
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import GateRecord, GATE_ORDER, Slot

BENCH = Path(__file__).resolve().parents[1] / "fixtures" / "bench"


def _load(name: str) -> dict:
    return json.loads((BENCH / name).read_text())


def _engine(tmp_path: Path, spec: dict) -> Engine:
    pace = spec.get("pace", "crawl")
    b = Budget.for_pace(pace)
    if spec.get("max_calls") is not None:
        b.max_calls = int(spec["max_calls"])
    return Engine(MemoryStore(tmp_path), budget=b)


def test_one_body(tmp_path: Path):
    spec = _load("one_body.json")
    m = element_at_rest(spec["id"], spec["effect"], spec["purpose"], spec["end_state"])
    result = _engine(tmp_path, spec).run_standing_order(
        m, look_update=spec["look"], operator_why="one body?"
    )
    assert result.mission.status.value == spec["expect"]["status"]
    assert result.mission.picture.worker_count() == 0
    assert result.split is False
    assert diagnose(m)["health"] == "ok"


def test_dead_plan(tmp_path: Path):
    spec = _load("dead_plan.json")
    m = element_at_rest(spec["id"], spec["effect"], spec["purpose"], spec["end_state"])
    result = _engine(tmp_path, spec).adapt_vector(
        m,
        look_update=spec["look"],
        report=spec["report"],
        new_method=spec["method"],
        axes=spec["axes"],
    )
    assert result.mission.status.value == "complete"
    assert result.mission.picture.worker_count() == 0
    assert spec["expect"]["method_contains"] in result.mission.picture.method


def test_two_sources(tmp_path: Path):
    spec = _load("two_sources.json")
    m = element_at_rest(spec["id"], spec["effect"], spec["purpose"], spec["end_state"])
    seams = [Seam(a, b) for a, b in spec["seams"]]
    result = _engine(tmp_path, spec).run_multi_axis(
        m,
        look_update=spec["look"],
        seams=seams,
        axes=spec["axes"],
        operator_why="two notes?",
    )
    assert result.split is True
    assert result.mission.picture.worker_count() == 2
    iso = diagnose(m)["isolation"]
    assert iso["flags"] == []


def test_already_exists():
    spec = _load("already_exists.json")
    m = element_at_rest(spec["id"], spec["effect"], spec["purpose"], spec["end_state"])
    world = World(existing_files=["out/summary.md"], existing_channels=["summary"])
    assert decide([Seam("summary", "need a summary writer")], world=world) is None
    bad = GateRecord(
        can_someone_else=True,
        should_we=True,
        named_failure="file already on disk",
        could_we=True,
        channel_id="summary",
        order=GATE_ORDER,
    )
    with pytest.raises(InvariantError) as e:
        m.write_who(
            "head-1",
            m.picture.slots + [Slot(id="w-summary", function="worker", channel_id="summary")],
            gates=bad,
        )
    assert e.value.code == spec["expect"]["code"]
    assert m.picture.worker_count() == 0


def test_leash(tmp_path: Path):
    spec = _load("leash.json")
    m = element_at_rest(spec["id"], spec["effect"], spec["purpose"], spec["end_state"])
    with pytest.raises(InvariantError) as e:
        _engine(tmp_path, spec).run_standing_order(
            m, look_update=spec["look"], operator_why="stop?"
        )
    assert e.value.code == spec["expect"]["code"]
    assert m.status.value == spec["expect"]["status"]


def test_every_fixture_meets_its_expect_block():
    from taskorg.bench import run_bench

    report = run_bench(BENCH)
    failed = [(r["id"], [c for c in r["checks"] if not c["ok"]]) for r in report["results"] if not r["ok"]]
    assert not failed, failed
    assert report["passed"] == len(list(BENCH.glob("*.json")))
