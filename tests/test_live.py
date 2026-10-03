import pytest

from taskorg.adapters import Brief
from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.live import ScriptedLive, _extract_json, artifact_from_model
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore


def _brief() -> Brief:
    return Brief(
        slot_function="worker",
        skill="execute",
        packet="doctrine only",
        effect="Complete the task",
        purpose="Keep the goal intact",
        picture="source-b open",
        end_state="held",
        channel_id="source-b",
    )


def test_good_json_becomes_artifact():
    data = _extract_json(
        '{"claim":"rear clear","evidence":["overlay"],"uncertainty":"rooms off hall","channel_id":"source-b","delta_to_picture":"rear held","requests":[]}'
    )
    art = artifact_from_model(data, _brief())
    assert art.channel_id == "source-b"
    assert art.claim == "rear clear"


def test_fenced_json_ok():
    data = _extract_json('```json\n{"claim":"x","evidence":[],"uncertainty":"n","channel_id":"c","delta_to_picture":"d","requests":[]}\n```')
    assert data["claim"] == "x"


def test_model_speaking_who_is_rejected():
    with pytest.raises(InvariantError) as e:
        artifact_from_model(
            {
                "claim": "I am reorganizing the team",
                "evidence": [],
                "uncertainty": "n",
                "channel_id": "c",
                "delta_to_picture": "d",
                "write_who": {"slots": ["army"]},
            },
            _brief(),
        )
    assert e.value.code == "WHO"


def test_empty_claim_rejected():
    with pytest.raises(InvariantError) as e:
        artifact_from_model({"claim": "  "}, _brief())
    assert e.value.code == "SCHEMA"


def test_scripted_adapter_drives_loop(tmp_path):
    replies = [
        '{"claim":"PASS default task drafted","evidence":["look","purpose"],"uncertainty":"stub-live","channel_id":"head-integrate","delta_to_picture":"order on paper","requests":[]}',
        '{"claim":"PASS","evidence":["default task","purpose"],"uncertainty":"none","channel_id":"verify","delta_to_picture":"verified","requests":[]}',
    ]
    store = MemoryStore(tmp_path)
    m = element_at_rest("live-001", "Issue order", "Picture holds", "Issued")
    result = Engine(store, adapter=ScriptedLive(replies)).run_standing_order(
        m,
        look_update="Enough picture",
        operator_why="Could this have been one?",
        head_reason="yes",
    )
    assert result.verified is True
    assert result.product.claim.startswith("PASS default")
    assert m.status.value == "complete"
    assert m.summary()["could_this_have_been_one"] is True
    assert m.picture.worker_count() == 0
