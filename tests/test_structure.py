from pathlib import Path

from taskorg.budget import Budget
from taskorg.factory import new_run
from taskorg.loop import Engine, score_criteria
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact


def test_context_changed_opens_second_review(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("st-1", "Write the report", "Keep the context", "Report written")
    Engine(store).run_single(m, context="other side visible", operator_question="one?")
    assert m.context_changed()
    assert "context-changed" in m.notes
    assert m.notes["context-changed"].status.value == "closed"
    assert any(d.stream == "report" for d in m.deltas)
    assert "report" in m.open_streams


def test_score_criteria_miss():
    product = Artifact(
        claim="did a thing",
        evidence=["none"],
        uncertainty="n",
        channel_id="lead-merge",
        context_update="x",
    )
    scored = score_criteria(product, ["default task", "purpose"])
    assert scored["score"] < 1
    assert scored["misses"]


def test_normal_sends_out(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("st-2", "Summarize the notes", "Keep sources apart", "Summary written")
    Engine(store, budget=Budget.for_tier("normal")).run_replan(
        m,
        context="the first source is stale",
        replan_reason="first plan is dead",
        new_method="reroute",
        axes=["reroute"],
    )
    assert any(d.stream == "report" for d in m.deltas)
    assert m.last_verify and m.last_verify["score"] == 1.0


def test_split_opens_adjacent_without_merging(tmp_path: Path):
    from taskorg.gates import Subtask

    store = MemoryStore(tmp_path)
    m = new_run("st-3", "Summarize the notes", "Keep sources apart", "Summary written")
    Engine(store, budget=Budget.for_tier("open")).run_fanout(
        m,
        context="two subtasks",
        subtasks=[Subtask("source-a", "source-a"), Subtask("source-b", "source-b")],
        axes=["sequential", "fan_in"],
        operator_question="method?",
    )
    assert any(d.stream == "peer" for d in m.deltas)
    assert "holding" not in (m.state.context or "")
