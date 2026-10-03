import pytest

from taskorg.cues import admit_cues, fire_auto_cues
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.models import RunState, Slot
from taskorg.run import Run


def test_switch_skill_sets_skill_tools():
    m = new_run("t1", "Summarize the notes", "Keep sources apart", "Summary written")
    m.switch_skill("lead-1", "lead-1", "observe", "context")
    assert "observe" in m.state.slot("lead-1").tools
    assert m.state.slot("lead-1").skill == "observe"


def test_assert_tools_rejects_unlisted():
    m = new_run("t2", "Summarize the notes", "Keep sources apart", "Summary written")
    m.switch_skill("lead-1", "lead-1", "draft", "write")
    with pytest.raises(InvariantError) as e:
        m.assert_tools("lead-1", ["spawn"])
    assert e.value.code == "TOOLS"
    m.assert_tools("lead-1", ["write"])


def test_complete_requires_how():
    lead = Slot(id="lead-1", function="lead")
    pic = RunState(
        lead_id="lead-1",
        slots=[lead],
        primary="lead-1",
        goal="x",
        success_criteria=["y"],
        cadence="now",
        checkpoints=[],
        context="here",
        done_when="there",
        purpose="why",
        method="",
    )
    m = Run(id="t3", state=pic)
    with pytest.raises(InvariantError) as e:
        m.complete()
    assert e.value.code == "SCHEMA"


def test_admit_cues_opens_review_that_must_be_answered():
    m = new_run("t4", "Summarize the notes", "Keep sources apart", "Summary written")
    m.update_context("lead-1", "enough")
    fire_auto_cues(m)
    opened = admit_cues(m)
    assert opened
    with pytest.raises(InvariantError):
        m.complete()
    for nid in opened:
        m.answer_review("lead-1", nid, "KEEP_ROSTER", "one slot is enough")
    m.complete()
