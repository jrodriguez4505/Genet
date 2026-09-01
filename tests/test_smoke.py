from pathlib import Path

from taskorg.budget import Budget
from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Slot


def test_one_body_completes(tmp_path: Path):
    store = MemoryStore(tmp_path)
    store.write_doctrine("standing", "one body first")
    m = element_at_rest("smoke", "Complete the default task", "Keep purpose", "Done")
    result = Engine(store, budget=Budget.for_pace("crawl")).run_standing_order(
        m,
        look_update="One source. Picture is enough.",
        operator_why="Could this have been one body?",
    )
    assert result.mission.status.value == "complete"
    assert result.mission.picture.worker_count() == 0
    assert result.verified


def test_worker_cannot_spawn():
    m = element_at_rest("x", "task", "purpose", "done")
    try:
        m.worker_spawn("w-1", Slot(id="w-2", function="worker"))
    except InvariantError as e:
        assert e.code == "INV-2"
    else:
        raise AssertionError("spawn must fail")


def test_crawl_cannot_split(tmp_path: Path):
    from taskorg.gates import Seam
    store = MemoryStore(tmp_path)
    m = element_at_rest("c", "task", "purpose", "done")
    try:
        Engine(store, budget=Budget.for_pace("crawl")).run_multi_axis(
            m,
            look_update="seam:a=a seam:b=b",
            seams=[Seam("a", "a"), Seam("b", "b")],
            axes=["sequential"],
            operator_why="why",
        )
    except InvariantError as e:
        assert e.code == "BUDGET"
    else:
        raise AssertionError("crawl must not split")
