import pytest

from taskorg.budget import Budget
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore


def test_max_calls_halts(tmp_path):
    store = MemoryStore(tmp_path)
    m = new_run("b1", "Write the report", "Keep the context", "Report written")
    with pytest.raises(InvariantError) as e:
        Engine(store, budget=Budget(max_calls=1)).run_single(
            m, context="enough", operator_question="one?"
        )
    assert e.value.code == "BUDGET"
    assert m.status.value == "abort"
    assert "max_calls" in m.stop_reason


def test_max_seconds_halts(tmp_path):
    store = MemoryStore(tmp_path)
    m = new_run("b2", "Write the report", "Keep the context", "Report written")
    with pytest.raises(InvariantError) as e:
        Engine(store, budget=Budget(max_seconds=0)).run_single(
            m, context="enough", operator_question="one?"
        )
    assert e.value.code == "BUDGET"
    assert "max_seconds" in m.stop_reason


def test_cannot_act_after_complete(tmp_path):
    store = MemoryStore(tmp_path)
    m = new_run("b3", "Write the report", "Keep the context", "Report written")
    Engine(store).run_single(m, context="enough", operator_question="one?")
    with pytest.raises(InvariantError) as e:
        m.assert_running()
    assert e.value.code == "BUDGET"


def test_human_halt():
    m = new_run("b4", "Write the report", "Keep the context", "Report written")
    with pytest.raises(InvariantError) as e:
        m.halt("operator kill switch")
    assert e.value.code == "BUDGET"
    assert m.status.value == "abort"


def test_tight_refuses_split(tmp_path):
    from taskorg.gates import Subtask

    store = MemoryStore(tmp_path)
    m = new_run("b5", "Summarize the notes", "Keep sources apart", "Summary written")
    with pytest.raises(InvariantError) as e:
        Engine(store, budget=Budget.for_tier("tight")).run_fanout(
            m,
            context="subtasks",
            subtasks=[Subtask("source-a", "x"), Subtask("source-b", "y")],
            axes=["sequential"],
            operator_question="?",
        )
    assert e.value.code == "BUDGET"
    assert "cannot fan out" in m.stop_reason


def test_tight_refuses_replan(tmp_path):
    store = MemoryStore(tmp_path)
    m = new_run("b6", "Summarize the notes", "Keep sources apart", "Summary written")
    with pytest.raises(InvariantError):
        Engine(store, budget=Budget.for_tier("tight")).run_replan(
            m,
            context="stale source",
            replan_reason="the plan no longer fits",
            new_method="reroute",
            axes=["reroute"],
        )
    assert "cannot replan" in m.stop_reason


def test_normal_forbids_split_only():
    normal = Budget.for_tier("normal")
    assert normal.allow_adapt is True
    assert normal.allow_split is False
    assert Budget.for_tier("open").allow_split is True
