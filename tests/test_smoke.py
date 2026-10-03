from pathlib import Path

from taskorg.budget import Budget
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Slot


def test_single_agent_completes(tmp_path: Path):
    store = MemoryStore(tmp_path)
    store.write_guidelines("standing", "one agent first")
    m = new_run("smoke", "Complete the default task", "Keep purpose", "Done")
    result = Engine(store, budget=Budget.for_tier("tight")).run_single(
        m,
        context="One source. The context is enough.",
        operator_question="Could a single agent have done this?",
    )
    assert result.run.status.value == "complete"
    assert result.run.state.worker_count() == 0
    assert result.verified


def test_worker_cannot_spawn():
    m = new_run("x", "task", "purpose", "done")
    try:
        m.worker_spawn("w-1", Slot(id="w-2", function="worker"))
    except InvariantError as e:
        assert e.code == "INV-2"
    else:
        raise AssertionError("spawn must fail")


def test_tight_cannot_split(tmp_path: Path):
    from taskorg.gates import Subtask
    store = MemoryStore(tmp_path)
    m = new_run("c", "task", "purpose", "done")
    try:
        Engine(store, budget=Budget.for_tier("tight")).run_fanout(
            m,
            context="subtask:a=a subtask:b=b",
            subtasks=[Subtask("a", "a"), Subtask("b", "b")],
            axes=["sequential"],
            operator_question="why",
        )
    except InvariantError as e:
        assert e.code == "BUDGET"
    else:
        raise AssertionError("the tight tier must not fan out")
