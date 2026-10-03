"""Proof we can still get without a model key."""

from pathlib import Path

import pytest

from taskorg.budget import Budget
from taskorg.cli import main  # noqa: F401
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.gates import Seam, decide
from taskorg.live import ScriptedLive
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import GateRecord, Slot
from taskorg.persist import load_mission


def test_cli_crawl_split_returns_one(tmp_path: Path, capsys):
    rc = main([
        "split",
        "--pace", "crawl",
        "--id", "nk-cli",
        "--store", str(tmp_path),
        "--out", str(tmp_path / "halt.json"),
        "--look", "seam:source-a=x seam:source-b=y",
        "--seams", "source-a:x,source-b:y",
    ])
    assert rc == 1
    out = capsys.readouterr().out
    assert "BUDGET" in out
    assert "cannot split" in out


def test_cli_max_calls_returns_one(tmp_path: Path, capsys):
    rc = main([
        "run",
        "--pace", "crawl",
        "--max-calls", "1",
        "--id", "nk-cap",
        "--store", str(tmp_path),
        "--out", str(tmp_path / "cap.json"),
        "--look", "enough",
    ])
    assert rc == 1
    assert "BUDGET" in capsys.readouterr().out


def test_cli_crawl_split_raises():
    from taskorg.loop import Engine
    from taskorg.memory_store import MemoryStore
    from pathlib import Path
    import tempfile

    store = MemoryStore(Path(tempfile.mkdtemp()))
    m = element_at_rest("nk-1", "Clear", "Deny", "Held")
    with pytest.raises(InvariantError) as e:
        Engine(store, budget=Budget.for_pace("crawl")).run_multi_axis(
            m,
            look_update="seam:source-a=x seam:source-b=y",
            seams=[Seam("source-a", "x"), Seam("source-b", "y")],
            axes=["sequential"],
            operator_why="?",
        )
    assert e.value.code == "BUDGET"


def test_someone_else_blocks_split():
    seams = [Seam("docs", "already written")]
    rec = decide(seams)
    # decide() currently always builds could-we last if we pass seams in.
    # Force the first gate by constructing an illegal record.
    bad = GateRecord(
        can_someone_else=True,
        should_we=True,
        named_failure="docs exist",
        could_we=True,
        channel_id="docs",
        order=("can_someone_else", "should_we", "could_we"),
    )
    m = element_at_rest("nk-2", "Clear", "Deny", "Held")
    with pytest.raises(InvariantError) as e:
        m.write_who(
            "head-1",
            m.picture.slots + [Slot(id="w-docs", function="worker", channel_id="docs")],
            gates=bad,
        )
    assert e.value.code == "GATE-1"


def test_recut_purpose_closes_plan_wrong():
    m = element_at_rest("nk-3", "Complete the task", "Keep the goal intact", "Held")
    m.report_plan_wrong("wrong building")
    m.respond_why("head-1", "plan-wrong", "REVISE_GOAL", "intent is now isolate not clear")
    assert m.notes["plan-wrong"].status.value == "closed"
    # purpose itself is recut only if we added that — method/purpose may still be original
    m.complete()
    assert m.status.value == "complete"


def test_scripted_live_walk_adapt(tmp_path: Path):
    replies = [
        '{"claim":"PASS new vector written","evidence":["look","default task","purpose"],"uncertainty":"script","channel_id":"head-integrate","delta_to_picture":"rear","requests":[]}',
        '{"claim":"PASS","evidence":["default task","purpose"],"uncertainty":"none","channel_id":"verify","delta_to_picture":"verified","requests":[]}',
    ]
    store = MemoryStore(tmp_path)
    m = element_at_rest("nk-4", "Clear", "Deny", "Held")
    result = Engine(store, adapter=ScriptedLive(replies), budget=Budget.for_pace("walk")).adapt_vector(
        m,
        look_update="first source is a decoy",
        report="first plan is dead",
        new_method="circumvent via rear",
        axes=["reroute"],
    )
    assert result.verified is True
    assert diagnose(m)["health"] == "ok"
    assert diagnose(m)["pace"]["name"] == "walk"


def test_diagnose_budget_halt(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("nk-5", "Issue order", "Picture", "Issued")
    with pytest.raises(InvariantError):
        Engine(store, budget=Budget(max_calls=1, pace="crawl", allow_split=False, allow_adapt=False)).run_standing_order(
            m, look_update="enough", operator_why="one?"
        )
    report = diagnose(m)
    assert m.status.value == "abort"
    assert "budget_halt" in report["flags"] or report["pace"]["stop_reason"]


def test_scripted_rejects_authority_keys():
    from taskorg.live import artifact_from_model
    from taskorg.adapters import Brief

    brief = Brief(
        slot_function="worker",
        skill="execute",
        packet="x",
        effect="e",
        purpose="p",
        picture="here",
        end_state="there",
    )
    with pytest.raises(InvariantError):
        artifact_from_model(
            {
                "claim": "ok",
                "evidence": [],
                "uncertainty": "n",
                "channel_id": "source-a",
                "delta_to_picture": "d",
                "requests": [],
                "write_who": True,
            },
            brief,
        )
