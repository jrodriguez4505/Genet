from pathlib import Path

import pytest

from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore


def test_keep_roster_illegal_on_replan():
    m = new_run("pw-1", "Summarize the notes", "Keep sources apart", "Summary written")
    m.update_context("lead-1", "the first source is stale")
    m.request_replan("the first plan no longer fits: the first source is stale")
    with pytest.raises(InvariantError) as e:
        m.answer_review("lead-1", "replan", "KEEP_ROSTER", "stay the course")
    assert e.value.code == "INV-14"


def test_complete_blocked_until_method_changes():
    m = new_run("pw-2", "Summarize the notes", "Keep sources apart", "Summary written")
    m.update_context("lead-1", "the first source is stale")
    m.request_replan("plan is wrong")
    with pytest.raises(InvariantError) as e:
        m.complete()
    assert e.value.code == "INV-14"


def test_change_method_clears_replan():
    m = new_run("pw-3", "Summarize the notes", "Keep sources apart", "Summary written")
    m.update_context("lead-1", "the first source is stale")
    m.request_replan("the plan no longer fits; switch to source-b")
    m.answer_review("lead-1", "replan", "CHANGE_METHOD", "work from source-b")
    assert m.state.method == "work from source-b"
    assert m.notes["replan"].status.value == "closed"
    m.complete()
    assert m.status.value == "complete"


def test_revise_purpose_when_the_goal_no_longer_fits():
    m = new_run("pw-4", "Summarize the dataset", "Keep the sources apart", "Summary written")
    m.request_replan("wrong dataset")
    m.answer_review("lead-1", "replan", "REVISE_GOAL", "Keep the other run separate")
    assert m.state.purpose == "Keep the other run separate"


def test_replan_requires_named_method():
    m = new_run("pw-empty", "Summarize the notes", "Keep sources apart", "Summary written")
    m.request_replan("plan is wrong")
    with pytest.raises(InvariantError) as e:
        m.answer_review("lead-1", "replan", "CHANGE_METHOD", "   ")
    assert e.value.code == "INV-14"


def test_replan_method_loop(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("pw-loop", "Summarize the notes", "Keep sources apart", "Summary written")
    result = Engine(store).run_replan(
        m,
        context="the first source is stale; source-b is current",
        replan_reason="first plan is dead",
        new_method="work from source-b",
        axes=["reroute", "reverse"],
    )
    assert m.state.method == "work from source-b"
    assert "reroute" in m.state.axes
    assert m.notes["replan"].response == "CHANGE_METHOD"
    assert m.status.value == "complete"
    assert result.verified is True
    assert m.summary()["replan_open"] is False
