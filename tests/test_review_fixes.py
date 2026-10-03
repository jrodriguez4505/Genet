import pytest

from taskorg.adapters import Brief
from taskorg.cues import fire_auto_cues
from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.live import artifact_from_model
from taskorg.models import Artifact


def test_worker_cannot_update_where():
    m = element_at_rest("rf-1", "Clear", "Deny", "Held")
    with pytest.raises(InvariantError) as e:
        m.update_context("worker-rogue", "other side")
    assert e.value.code == "INV-1"


def test_unknown_json_keys_rejected():
    brief = Brief(
        slot_function="worker",
        skill="execute",
        packet="x",
        effect="e",
        purpose="p",
        picture="here",
        end_state="there",
    )
    with pytest.raises(InvariantError) as e:
        artifact_from_model(
            {
                "claim": "ok",
                "evidence": [],
                "uncertainty": "n",
                "channel_id": "source-a",
                "delta_to_picture": "d",
                "requests": [],
                "temperature": 0.2,
            },
            brief,
        )
    assert e.value.code == "SCHEMA"


def test_cue_targets_living_head():
    m = element_at_rest("rf-2", "Clear", "Deny", "Held")
    m.update_context(m.picture.who_head_id, "enough")
    fire_auto_cues(m)
    for cue in m.cues.values():
        assert cue.target == m.picture.who_head_id


def test_unlisted_tool_request_rejected():
    m = element_at_rest("rf-3", "Clear", "Deny", "Held")
    m.slide("head-1", "head-1", "draft", "write")
    with pytest.raises(InvariantError) as e:
        m.assert_tools("head-1", ["spawn"])
    assert e.value.code == "TOOLS"
