from pathlib import Path

import pytest

from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.gates import Subtask, decide
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore


def test_no_subtasks_means_no_split():
    assert decide([Subtask("source-a", "x", covered_by_existing=True)]) is None


def test_uncovered_subtask_passes_gates():
    rec = decide([Subtask("source-b", "independent source-b channel")])
    assert rec is not None
    assert rec.channel_id == "source-b"
    assert rec.order[0] == "can_someone_else"


def test_multi_axis_isolated_channels(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("p2-split", "Complete the task", "Keep the goal intact", "Task finished")
    result = Engine(store).run_fanout(
        m,
        context="Primary path blocked. Two sources are independent.",
        subtasks=[
            Subtask("source-a", "independent source-a channel"),
            Subtask("source-b", "independent source-b channel"),
        ],
        axes=["parallel", "reverse", "fan_in"],
        operator_question="Why keep a single agent at all?",
    )
    assert result.split is True
    assert result.channels == ["source-a", "source-b"]
    assert m.state.worker_count() == 2
    assert m.summary()["could_this_have_been_one"] is False
    worker_arts = [a for a in m.artifacts if a.channel_id in ("source-a", "source-b")]
    assert {a.channel_id for a in worker_arts} == {"source-a", "source-b"}
    assert any("source-a" in a.claim for a in worker_arts)
    assert any("source-b" in a.claim for a in worker_arts)
    assert "conflict-" + m.id in m.cues
    assert m.status.value == "complete"
    assert "fan_in" in m.state.axes


def test_context_without_subtasks_stays_one(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("p2-one", "Write the order", "Shared context", "Task recorded")
    result = Engine(store).run_fanout(
        m,
        context="One room. No second subtask.",
        subtasks=[Subtask("only", "none", covered_by_existing=True)],
        axes=["parallel"],
        operator_question="Could this have been one?",
        lead_response="KEEP_ROSTER",
        lead_reason="yes",
    )
    assert result.split is False
    assert m.state.worker_count() == 0
    assert m.summary()["could_this_have_been_one"] is True


def test_split_still_cannot_skip_the_context_rule(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("p2-explore", "Summarize the notes", "Keep sources apart", "Summary written")
    m.update_context("lead-1", "the context is already complete")
    from taskorg.models import GateRecord, Slot

    rec = GateRecord(
        can_someone_else=False,
        should_we=True,
        named_failure="need a look",
        could_we=True,
        channel_id="explore",
    )
    with pytest.raises(InvariantError) as e:
        m.request_exploratory_spawn(
            "lead-1",
            Slot(id="w-explore", function="worker", skill="observe", channel_id="explore"),
            rec,
        )
    assert e.value.code == "INV-10"
