import pytest

from taskorg.budget import Budget
from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore


def test_max_calls_halts(tmp_path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("b1", "Issue order", "Picture", "Issued")
    with pytest.raises(InvariantError) as e:
        Engine(store, budget=Budget(max_calls=1)).run_standing_order(
            m, look_update="enough", operator_why="one?"
        )
    assert e.value.code == "BUDGET"
    assert m.status.value == "abort"
    assert "max_calls" in m.stop_reason


def test_max_seconds_halts(tmp_path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("b2", "Issue order", "Picture", "Issued")
    with pytest.raises(InvariantError) as e:
        Engine(store, budget=Budget(max_seconds=0)).run_standing_order(
            m, look_update="enough", operator_why="one?"
        )
    assert e.value.code == "BUDGET"
    assert "max_seconds" in m.stop_reason


def test_cannot_act_after_complete(tmp_path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("b3", "Issue order", "Picture", "Issued")
    Engine(store).run_standing_order(m, look_update="enough", operator_why="one?")
    with pytest.raises(InvariantError) as e:
        m.assert_running()
    assert e.value.code == "BUDGET"


def test_human_halt():
    m = element_at_rest("b4", "Issue order", "Picture", "Issued")
    with pytest.raises(InvariantError) as e:
        m.halt("operator kill switch")
    assert e.value.code == "BUDGET"
    assert m.status.value == "abort"


def test_crawl_refuses_split(tmp_path):
    from taskorg.gates import Seam

    store = MemoryStore(tmp_path)
    m = element_at_rest("b5", "Clear", "Deny", "Held")
    with pytest.raises(InvariantError) as e:
        Engine(store, budget=Budget.for_pace("crawl")).run_multi_axis(
            m,
            look_update="seams",
            seams=[Seam("source-a", "x"), Seam("source-b", "y")],
            axes=["sequential"],
            operator_why="?",
        )
    assert e.value.code == "BUDGET"
    assert "cannot split" in m.stop_reason


def test_crawl_refuses_adapt(tmp_path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("b6", "Clear", "Deny", "Held")
    with pytest.raises(InvariantError):
        Engine(store, budget=Budget.for_pace("crawl")).adapt_vector(
            m,
            look_update="decoy",
            report="plan wrong",
            new_method="reroute",
            axes=["reroute"],
        )
    assert "cannot adapt" in m.stop_reason


def test_walk_forbids_split_only():
    walk = Budget.for_pace("walk")
    assert walk.allow_adapt is True
    assert walk.allow_split is False
    assert Budget.for_pace("run").allow_split is True
