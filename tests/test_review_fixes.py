import pytest

from taskorg.adapters import Brief
from taskorg.cues import fire_auto_cues
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.live import artifact_from_model
from taskorg.models import Artifact


def test_worker_cannot_update_where():
    m = new_run("rf-1", "Summarize the notes", "Keep sources apart", "Summary written")
    with pytest.raises(InvariantError) as e:
        m.update_context("worker-rogue", "other side")
    assert e.value.code == "INV-1"


def test_unknown_json_keys_rejected():
    brief = Brief(
        slot_function="worker",
        skill="execute",
        packet="x",
        goal="e",
        purpose="p",
        context="here",
        done_when="there",
    )
    with pytest.raises(InvariantError) as e:
        artifact_from_model(
            {
                "claim": "ok",
                "evidence": [],
                "uncertainty": "n",
                "channel_id": "source-a",
                "context_update": "d",
                "requests": [],
                "temperature": 0.2,
            },
            brief,
        )
    assert e.value.code == "SCHEMA"


def test_cue_targets_living_head():
    m = new_run("rf-2", "Summarize the notes", "Keep sources apart", "Summary written")
    m.update_context(m.state.lead_id, "enough")
    fire_auto_cues(m)
    for cue in m.cues.values():
        assert cue.target == m.state.lead_id


def test_unlisted_tool_request_rejected():
    m = new_run("rf-3", "Summarize the notes", "Keep sources apart", "Summary written")
    m.switch_skill("lead-1", "lead-1", "draft", "write")
    with pytest.raises(InvariantError) as e:
        m.assert_tools("lead-1", ["spawn"])
    assert e.value.code == "TOOLS"
