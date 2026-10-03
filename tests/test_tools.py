import pytest

from taskorg.cues import admit_cues, fire_auto_cues
from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.models import FiveWH, Slot
from taskorg.mission import Mission


def test_slide_sets_qual_tools():
    m = element_at_rest("t1", "Clear", "Deny", "Held")
    m.slide("head-1", "head-1", "observe", "look")
    assert "observe" in m.picture.slot("head-1").tools
    assert m.picture.slot("head-1").skill == "observe"


def test_assert_tools_rejects_unlisted():
    m = element_at_rest("t2", "Clear", "Deny", "Held")
    m.slide("head-1", "head-1", "draft", "write")
    with pytest.raises(InvariantError) as e:
        m.assert_tools("head-1", ["spawn"])
    assert e.value.code == "TOOLS"
    m.assert_tools("head-1", ["write"])


def test_complete_requires_how():
    head = Slot(id="head-1", function="head")
    pic = FiveWH(
        who_head_id="head-1",
        slots=[head],
        primary="head-1",
        effect="x",
        success_criteria=["y"],
        tempo="now",
        decision_points=[],
        current_picture="here",
        end_state="there",
        purpose="why",
        method="",
    )
    m = Mission(id="t3", picture=pic)
    with pytest.raises(InvariantError) as e:
        m.complete()
    assert e.value.code == "SCHEMA"


def test_admit_cues_opens_why_that_must_be_answered():
    m = element_at_rest("t4", "Clear", "Deny", "Held")
    m.update_context("head-1", "enough")
    fire_auto_cues(m)
    opened = admit_cues(m)
    assert opened
    with pytest.raises(InvariantError):
        m.complete()
    for nid in opened:
        m.respond_why("head-1", nid, "KEEP_ROSTER", "one slot is enough")
    m.complete()
