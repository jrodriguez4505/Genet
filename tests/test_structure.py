from pathlib import Path

from taskorg.budget import Budget
from taskorg.factory import element_at_rest
from taskorg.loop import Engine, score_criteria
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact


def test_picture_moved_opens_second_why(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("st-1", "Issue order", "Hold picture", "Issued")
    Engine(store).run_standing_order(m, look_update="other side visible", operator_why="one?")
    assert m.picture_moved()
    assert "why-picture" in m.notes
    assert m.notes["why-picture"].status.value == "closed"
    assert any(d.net == "out" for d in m.deltas)
    assert "out" in m.open_nets


def test_score_criteria_miss():
    product = Artifact(
        claim="did a thing",
        evidence=["none"],
        uncertainty="n",
        channel_id="head-integrate",
        delta_to_picture="x",
    )
    scored = score_criteria(product, ["default task", "purpose"])
    assert scored["score"] < 1
    assert scored["misses"]


def test_walk_sends_out(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("st-2", "Clear", "Deny", "Held")
    Engine(store, budget=Budget.for_pace("walk")).adapt_vector(
        m,
        look_update="first source is a decoy",
        report="first plan is dead",
        new_method="reroute",
        axes=["reroute"],
    )
    assert any(d.net == "out" for d in m.deltas)
    assert m.last_verify and m.last_verify["score"] == 1.0


def test_split_opens_adjacent_without_merging(tmp_path: Path):
    from taskorg.gates import Seam

    store = MemoryStore(tmp_path)
    m = element_at_rest("st-3", "Clear", "Deny", "Held")
    Engine(store, budget=Budget.for_pace("run")).run_multi_axis(
        m,
        look_update="two seams",
        seams=[Seam("source-a", "source-a"), Seam("source-b", "rear")],
        axes=["sequential", "fan_in"],
        operator_why="vector?",
    )
    assert any(d.net == "adjacent" for d in m.deltas)
    assert "holding" not in (m.picture.current_picture or "")
