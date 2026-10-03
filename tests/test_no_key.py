"""Proof we can still get without a model key."""

from pathlib import Path

import pytest

from taskorg.budget import Budget
from taskorg.cli import main  # noqa: F401
from taskorg.diagnostics import diagnose
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.gates import Subtask, decide
from taskorg.live import ScriptedLive
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import GateRecord, Slot
from taskorg.persist import load_run


def test_cli_tight_split_returns_one(tmp_path: Path, capsys):
    rc = main([
        "fanout",
        "--tier", "tight",
        "--id", "nk-cli",
        "--store", str(tmp_path),
        "--out", str(tmp_path / "halt.json"),
        "--context", "subtask:source-a=x subtask:source-b=y",
        "--subtasks", "source-a:x,source-b:y",
    ])
    assert rc == 1
    out = capsys.readouterr().out
    assert "BUDGET" in out
    assert "cannot fan out" in out


def test_cli_max_calls_returns_one(tmp_path: Path, capsys):
    rc = main([
        "single",
        "--tier", "tight",
        "--max-calls", "1",
        "--id", "nk-cap",
        "--store", str(tmp_path),
        "--out", str(tmp_path / "cap.json"),
        "--context", "enough",
    ])
    assert rc == 1
    assert "BUDGET" in capsys.readouterr().out


def test_cli_tight_split_raises():
    from taskorg.loop import Engine
    from taskorg.memory_store import MemoryStore
    from pathlib import Path
    import tempfile

    store = MemoryStore(Path(tempfile.mkdtemp()))
    m = new_run("nk-1", "Summarize the notes", "Keep sources apart", "Summary written")
    with pytest.raises(InvariantError) as e:
        Engine(store, budget=Budget.for_tier("tight")).run_fanout(
            m,
            context="subtask:source-a=x subtask:source-b=y",
            subtasks=[Subtask("source-a", "x"), Subtask("source-b", "y")],
            axes=["sequential"],
            operator_question="?",
        )
    assert e.value.code == "BUDGET"


def test_someone_else_blocks_split():
    subtasks = [Subtask("docs", "already written")]
    rec = decide(subtasks)
    # decide() currently always builds could-we last if we pass subtasks in.
    # Force the first gate by constructing an illegal record.
    bad = GateRecord(
        can_someone_else=True,
        should_we=True,
        named_failure="docs exist",
        could_we=True,
        channel_id="docs",
        order=("can_someone_else", "should_we", "could_we"),
    )
    m = new_run("nk-2", "Summarize the notes", "Keep sources apart", "Summary written")
    with pytest.raises(InvariantError) as e:
        m.set_roster(
            "lead-1",
            m.state.slots + [Slot(id="w-docs", function="worker", channel_id="docs")],
            gates=bad,
        )
    assert e.value.code == "GATE-1"


def test_recut_purpose_closes_replan():
    m = new_run("nk-3", "Complete the task", "Keep the goal intact", "Held")
    m.request_replan("wrong dataset")
    m.answer_review("lead-1", "replan", "REVISE_GOAL", "the purpose is now to isolate, not to summarize")
    assert m.notes["replan"].status.value == "closed"
    # purpose itself is recut only if we added that — method/purpose may still be original
    m.complete()
    assert m.status.value == "complete"


def test_scripted_live_normal_replan(tmp_path: Path):
    replies = [
        '{"claim":"PASS new method written","evidence":["context","default task","purpose"],"uncertainty":"script","channel_id":"lead-merge","context_update":"source-b","requests":[]}',
        '{"claim":"PASS","evidence":["default task","purpose"],"uncertainty":"none","channel_id":"verify","context_update":"verified","requests":[]}',
    ]
    store = MemoryStore(tmp_path)
    m = new_run("nk-4", "Summarize the notes", "Keep sources apart", "Summary written")
    result = Engine(store, adapter=ScriptedLive(replies), budget=Budget.for_tier("normal")).run_replan(
        m,
        context="the first source is stale",
        replan_reason="first plan is dead",
        new_method="work from source-b",
        axes=["reroute"],
    )
    assert result.verified is True
    assert diagnose(m)["health"] == "ok"
    assert diagnose(m)["tier"]["name"] == "normal"


def test_diagnose_budget_halt(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("nk-5", "Write the report", "Keep the context", "Report written")
    with pytest.raises(InvariantError):
        Engine(store, budget=Budget(max_calls=1, tier="tight", allow_split=False, allow_adapt=False)).run_single(
            m, context="enough", operator_question="one?"
        )
    report = diagnose(m)
    assert m.status.value == "abort"
    assert "budget_halt" in report["flags"] or report["tier"]["stop_reason"]


def test_scripted_rejects_authority_keys():
    from taskorg.live import artifact_from_model
    from taskorg.adapters import Brief

    brief = Brief(
        slot_function="worker",
        skill="execute",
        packet="x",
        goal="e",
        purpose="p",
        context="here",
        done_when="there",
    )
    with pytest.raises(InvariantError):
        artifact_from_model(
            {
                "claim": "ok",
                "evidence": [],
                "uncertainty": "n",
                "channel_id": "source-a",
                "context_update": "d",
                "requests": [],
                "set_roster": True,
            },
            brief,
        )
