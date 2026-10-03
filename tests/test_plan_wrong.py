from pathlib import Path

import pytest

from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore


def test_hold_org_illegal_on_plan_wrong():
    m = element_at_rest("pw-1", "Clear", "Deny", "Held")
    m.update_context("head-1", "first source is a decoy")
    m.report_plan_wrong("first plan is dead — first source is a decoy")
    with pytest.raises(InvariantError) as e:
        m.respond_why("head-1", "plan-wrong", "KEEP_ROSTER", "stay the course")
    assert e.value.code == "INV-14"


def test_complete_blocked_until_vector_changes():
    m = element_at_rest("pw-2", "Clear", "Deny", "Held")
    m.update_context("head-1", "first source is a decoy")
    m.report_plan_wrong("plan is wrong")
    with pytest.raises(InvariantError) as e:
        m.complete()
    assert e.value.code == "INV-14"


def test_change_how_clears_plan_wrong():
    m = element_at_rest("pw-3", "Clear", "Deny", "Held")
    m.update_context("head-1", "first source is a decoy")
    m.report_plan_wrong("plan is wrong — flex to rear")
    m.respond_why("head-1", "plan-wrong", "CHANGE_METHOD", "circumvent via source-b")
    assert m.picture.method == "circumvent via source-b"
    assert m.notes["plan-wrong"].status.value == "closed"
    m.complete()
    assert m.status.value == "complete"


def test_recut_purpose_when_what_is_dead():
    m = element_at_rest("pw-4", "Clear this building", "Deny this threat", "Held")
    m.report_plan_wrong("wrong building")
    m.respond_why("head-1", "plan-wrong", "REVISE_GOAL", "Deny the adjacent compound")
    assert m.picture.purpose == "Deny the adjacent compound"


def test_plan_wrong_requires_named_vector():
    m = element_at_rest("pw-empty", "Clear", "Deny", "Held")
    m.report_plan_wrong("plan is wrong")
    with pytest.raises(InvariantError) as e:
        m.respond_why("head-1", "plan-wrong", "CHANGE_METHOD", "   ")
    assert e.value.code == "INV-14"


def test_adapt_vector_loop(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("pw-loop", "Clear", "Deny", "Held")
    result = Engine(store).adapt_vector(
        m,
        look_update="first source is a decoy; source-b open",
        report="first plan is dead",
        new_method="circumvent via source-b",
        axes=["reroute", "reverse"],
    )
    assert m.picture.method == "circumvent via source-b"
    assert "reroute" in m.picture.axes
    assert m.notes["plan-wrong"].response == "CHANGE_METHOD"
    assert m.status.value == "complete"
    assert result.verified is True
    assert m.summary()["plan_wrong_open"] is False
