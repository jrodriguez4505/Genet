import pytest

from taskorg.adapters import Brief
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.live import ScriptedLive, _extract_json, artifact_from_model
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore


def _brief() -> Brief:
    return Brief(
        slot_function="worker",
        skill="execute",
        packet="guidelines only",
        goal="Complete the task",
        purpose="Keep the goal intact",
        context="source-b open",
        done_when="held",
        channel_id="source-b",
    )


def test_good_json_becomes_artifact():
    data = _extract_json(
        '{"claim":"note B checked","evidence":["index"],"uncertainty":"sections not yet read","channel_id":"source-b","context_update":"note B done","requests":[]}'
    )
    art = artifact_from_model(data, _brief())
    assert art.channel_id == "source-b"
    assert art.claim == "note B checked"


def test_fenced_json_ok():
    data = _extract_json('```json\n{"claim":"x","evidence":[],"uncertainty":"n","channel_id":"c","context_update":"d","requests":[]}\n```')
    assert data["claim"] == "x"


def test_model_speaking_who_is_rejected():
    with pytest.raises(InvariantError) as e:
        artifact_from_model(
            {
                "claim": "I am reorganizing the team",
                "evidence": [],
                "uncertainty": "n",
                "channel_id": "c",
                "context_update": "d",
                "set_roster": {"slots": ["army"]},
            },
            _brief(),
        )
    assert e.value.code == "ROSTER"


def test_empty_claim_rejected():
    with pytest.raises(InvariantError) as e:
        artifact_from_model({"claim": "  "}, _brief())
    assert e.value.code == "SCHEMA"


def test_scripted_replaner_drives_loop(tmp_path):
    replies = [
        '{"claim":"PASS default task drafted","evidence":["context","purpose"],"uncertainty":"stub-live","channel_id":"lead-merge","context_update":"report on paper","requests":[]}',
        '{"claim":"PASS","evidence":["default task","purpose"],"uncertainty":"none","channel_id":"verify","context_update":"verified","requests":[]}',
    ]
    store = MemoryStore(tmp_path)
    m = new_run("live-001", "Write the report", "Context holds", "Report written")
    result = Engine(store, adapter=ScriptedLive(replies)).run_single(
        m,
        context="Context is enough",
        operator_question="Could this have been one?",
        lead_reason="yes",
    )
    assert result.verified is True
    assert result.product.claim.startswith("PASS default")
    assert m.status.value == "complete"
    assert m.summary()["could_this_have_been_one"] is True
    assert m.state.worker_count() == 0
