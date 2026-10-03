from pathlib import Path

import pytest

from taskorg.budget import Budget
from taskorg.cli import main
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import GateRecord, Slot
from taskorg.persist import load_run, save_run


def test_one_write_who_cannot_add_two_workers():
    m = new_run("pr-1", "Summarize the notes", "Keep sources apart", "Summary written")
    gates = GateRecord(
        can_someone_else=False,
        should_we=True,
        named_failure="two subtasks",
        could_we=True,
        channel_id="source-a",
        order=("can_someone_else", "should_we", "could_we"),
    )
    extra = [
        Slot(id="w-source-a", function="worker", channel_id="source-a"),
        Slot(id="w-source-b", function="worker", channel_id="source-b"),
    ]
    with pytest.raises(InvariantError) as e:
        m.set_roster("lead-1", m.state.slots + extra, gates=gates)
    assert e.value.code == "INV-8"


def test_normal_replan_completes(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("pr-2", "Summarize the notes", "Keep sources apart", "Summary written")
    result = Engine(store, budget=Budget.for_tier("normal")).run_replan(
        m,
        context="the first source is stale",
        replan_reason="first plan is dead",
        new_method="work from source-b",
        axes=["reroute"],
    )
    assert result.run.status.value == "complete"
    assert m.state.method == "work from source-b"
    assert diagnose(m)["tier"]["name"] == "normal"
    assert diagnose(m)["health"] == "ok"
    assert m.state.worker_count() == 0


def test_tier_survives_disk(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("pr-3", "Write the report", "Keep the context", "Report written")
    Engine(store, budget=Budget.for_tier("tight")).run_single(
        m, context="enough", operator_question="one?"
    )
    path = tmp_path / "pr-3.json"
    save_run(m, path)
    loaded = load_run(path)
    report = diagnose(loaded)
    assert report["tier"]["name"] == "tight"
    assert report["tier"]["allow_split"] is False
    assert report["health"] == "ok"


def test_cli_tight_is_default(tmp_path: Path, capsys):
    out = tmp_path / "so.json"
    rc = main([
        "single",
        "--id", "pr-cli",
        "--store", str(tmp_path),
        "--out", str(out),
        "--context", "context is enough",
    ])
    assert rc == 0
    m = load_run(out)
    assert m.budget.tier == "tight"
    assert diagnose(m)["tier"]["name"] == "tight"
