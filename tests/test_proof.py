from pathlib import Path

import pytest

from taskorg.budget import Budget
from taskorg.cli import main
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import GateRecord, Slot
from taskorg.persist import load_mission, save_mission


def test_one_write_who_cannot_add_two_workers():
    m = element_at_rest("pr-1", "Clear", "Deny", "Held")
    gates = GateRecord(
        can_someone_else=False,
        should_we=True,
        named_failure="two seams",
        could_we=True,
        channel_id="source-a",
        order=("can_someone_else", "should_we", "could_we"),
    )
    extra = [
        Slot(id="w-source-a", function="worker", channel_id="source-a"),
        Slot(id="w-rear", function="worker", channel_id="source-b"),
    ]
    with pytest.raises(InvariantError) as e:
        m.write_who("head-1", m.picture.slots + extra, gates=gates)
    assert e.value.code == "INV-8"


def test_walk_adapt_completes(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("pr-2", "Clear", "Deny", "Held")
    result = Engine(store, budget=Budget.for_pace("walk")).adapt_vector(
        m,
        look_update="first source is a decoy",
        report="first plan is dead",
        new_method="circumvent via rear",
        axes=["reroute"],
    )
    assert result.mission.status.value == "complete"
    assert m.picture.method == "circumvent via rear"
    assert diagnose(m)["pace"]["name"] == "walk"
    assert diagnose(m)["health"] == "ok"
    assert m.picture.worker_count() == 0


def test_pace_survives_disk(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("pr-3", "Issue order", "Picture", "Issued")
    Engine(store, budget=Budget.for_pace("crawl")).run_standing_order(
        m, look_update="enough", operator_why="one?"
    )
    path = tmp_path / "pr-3.json"
    save_mission(m, path)
    loaded = load_mission(path)
    report = diagnose(loaded)
    assert report["pace"]["name"] == "crawl"
    assert report["pace"]["allow_split"] is False
    assert report["health"] == "ok"


def test_cli_crawl_is_default(tmp_path: Path, capsys):
    out = tmp_path / "so.json"
    rc = main([
        "run",
        "--id", "pr-cli",
        "--store", str(tmp_path),
        "--out", str(out),
        "--look", "enough picture",
    ])
    assert rc == 0
    m = load_mission(out)
    assert m.budget.pace == "crawl"
    assert diagnose(m)["pace"]["name"] == "crawl"
