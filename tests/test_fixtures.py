"""Phase 0 fixtures. These must fail closed."""

import pytest

from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.models import Artifact, Cue, GateRecord, Slot


def legal_gates(channel: str, failure: str = "context overflow") -> GateRecord:
    return GateRecord(
        can_someone_else=False,
        should_we=True,
        named_failure=failure,
        could_we=True,
        channel_id=channel,
        order=("can_someone_else", "should_we", "could_we"),
    )


def test_mutiny_worker_cannot_change_who():
    m = element_at_rest("fx-mutiny", "complete the task", "keep the goal intact", "task finished")
    with pytest.raises(InvariantError) as e:
        m.write_who("worker-rogue", m.picture.slots + [Slot(id="w1", function="worker", channel_id="east")])
    assert e.value.code == "INV-1"


def test_mutiny_worker_cannot_spawn():
    m = element_at_rest("fx-spawn", "complete the task", "keep the goal intact", "task finished")
    with pytest.raises(InvariantError) as e:
        m.worker_spawn("worker-1", Slot(id="w2", function="worker", channel_id="west"))
    assert e.value.code == "INV-2"


def test_why_cannot_seize_command():
    m = element_at_rest("fx-why-mutiny", "complete the task", "keep the goal intact", "task finished")
    m.submit_why("cheaper failure: the door is a decoy", "n1")
    with pytest.raises(InvariantError) as e:
        m.why_seize_command("n1")
    assert e.value.code == "WHY"


def test_why_cannot_halt():
    m = element_at_rest("fx-why-halt", "complete the task", "keep the goal intact", "task finished")
    with pytest.raises(InvariantError) as e:
        m.why_halt()
    assert e.value.code == "WHY"


def test_complete_with_open_note_fails():
    m = element_at_rest("fx-open-note", "complete the task", "keep the goal intact", "task finished")
    m.submit_why("why this entry and not the source-a", "n1")
    with pytest.raises(InvariantError) as e:
        m.complete()
    assert e.value.code == "INV-4"


def test_defer_then_complete_ok():
    m = element_at_rest("fx-defer", "complete the task", "keep the goal intact", "task finished")
    m.submit_why("later", "n1")
    m.respond_why("head-1", "n1", "DEFER", "hold until after look")
    m.complete()
    assert m.status.value == "complete"


def test_split_without_failure_refused():
    m = element_at_rest("fx-no-failure", "complete the task", "keep the goal intact", "task finished")
    bad = GateRecord(
        can_someone_else=False,
        should_we=False,
        named_failure=None,
        could_we=True,
        channel_id="east",
    )
    with pytest.raises(InvariantError) as e:
        m.write_who(
            "head-1",
            m.picture.slots + [Slot(id="w1", function="worker", channel_id="east")],
            gates=bad,
        )
    assert e.value.code == "INV-8"


def test_gate_order_violation_refused():
    m = element_at_rest("fx-gate-order", "complete the task", "keep the goal intact", "task finished")
    bad = GateRecord(
        can_someone_else=False,
        should_we=True,
        named_failure="context overflow",
        could_we=True,
        channel_id="east",
        order=("could_we", "should_we", "can_someone_else"),
    )
    with pytest.raises(InvariantError) as e:
        m.write_who(
            "head-1",
            m.picture.slots + [Slot(id="w1", function="worker", channel_id="east")],
            gates=bad,
        )
    assert e.value.code == "INV-9"


def test_can_someone_else_blocks_spawn():
    m = element_at_rest("fx-someone-else", "complete the task", "keep the goal intact", "task finished")
    bad = GateRecord(
        can_someone_else=True,
        should_we=True,
        named_failure="want another body",
        could_we=True,
        channel_id="east",
    )
    with pytest.raises(InvariantError) as e:
        m.write_who(
            "head-1",
            m.picture.slots + [Slot(id="w1", function="worker", channel_id="east")],
            gates=bad,
        )
    assert e.value.code == "GATE-1"


def test_recon_spawn_when_we_can_see_fails():
    m = element_at_rest("fx-recon", "complete the task", "keep the goal intact", "task finished")
    m.update_context("head-1", "second source visible, two seams")
    with pytest.raises(InvariantError) as e:
        m.request_recon_spawn(
            "head-1",
            Slot(id="w-recon", function="worker", skill="observe", channel_id="recon"),
            legal_gates("recon", "need eyes"),
        )
    assert e.value.code == "INV-10"


def test_recon_spawn_when_observe_qual_exists_fails():
    m = element_at_rest("fx-observe-exists", "complete the task", "keep the goal intact", "task finished")
    m.slide("head-1", "head-1", "observe", "look through the door from here")
    with pytest.raises(InvariantError) as e:
        m.request_recon_spawn(
            "head-1",
            Slot(id="w-recon", function="worker", skill="observe", channel_id="recon"),
            legal_gates("recon"),
        )
    assert e.value.code == "INV-10"


def test_slide_is_not_a_new_identity():
    m = element_at_rest("fx-slide", "complete the task", "keep the goal intact", "task finished")
    m.slide("head-1", "head-1", "retrieve", "pull the overlay")
    assert m.picture.slot("head-1").function == "head"
    assert m.picture.slot("head-1").skill == "retrieve"
    assert m.picture.worker_count() == 0


def test_legal_split_after_look_and_gates():
    m = element_at_rest("fx-legal-split", "complete the task", "keep the goal intact", "task finished")
    m.update_context("head-1", "primary path blocked; two sources are open")
    m.slide("head-1", "head-1", "reason", "pick How")
    m.set_how("head-1", "multi-axis", ["parallel", "reverse", "fan_in"])
    gates = legal_gates("source-b", "independent source-b channel")
    m.write_who(
        "head-1",
        m.picture.slots + [Slot(id="w-rear", function="worker", skill="execute", channel_id="source-b")],
        gates=gates,
    )
    m.accept_artifact(
        Artifact(
            claim="source-b clear to second deck",
            evidence=["observe overlay"],
            uncertainty="rooms off the hall unknown",
            channel_id="source-b",
            delta_to_picture="source-b held",
        )
    )
    m.submit_why("why not circumvent entirely", "n1")
    m.respond_why("head-1", "n1", "CHANGE_METHOD", "hold multi-axis")
    m.complete()
    s = m.summary()
    assert s["workers"] == 1
    assert s["could_this_have_been_one"] is False
    assert s["looked_through_door"] is True
    assert "fan_in" in s["how_axes"]


def test_single_agent_complete_could_have_been_one():
    m = element_at_rest("fx-one", "write the order", "shared picture", "order issued")
    m.update_context("head-1", "enough picture to write")
    m.complete()
    assert m.summary()["could_this_have_been_one"] is True


def test_verifier_cannot_pass_failed_stop():
    m = element_at_rest("fx-stop", "complete the task", "keep the goal intact", "task finished")
    m.mark_stop_rule_failed("success_criteria[0]")
    with pytest.raises(InvariantError) as e:
        m.verifier_pass_with_failed_stop()
    assert e.value.code == "INV-5"
    with pytest.raises(InvariantError):
        m.complete()


def test_memory_cannot_dump():
    m = element_at_rest("fx-dump", "complete the task", "keep the goal intact", "task finished")
    with pytest.raises(InvariantError) as e:
        m.dump_unscoped_history_into_brief()
    assert e.value.code == "INV-6"


def test_cue_requires_expiry():
    m = element_at_rest("fx-cue", "complete the task", "keep the goal intact", "task finished")
    with pytest.raises(InvariantError):
        m.mint_cue(Cue(id="c1", trigger="rework twice", payload="method exhausted", target="head-1", expiry=""))
    m.mint_cue(Cue(id="c1", trigger="rework twice", payload="method exhausted", target="head-1", expiry="mission-end"))
    assert "c1" in m.cues


def test_human_override_is_logged():
    m = element_at_rest("fx-human", "complete the task", "keep the goal intact", "task finished")
    m.write_who(
        "operator",
        m.picture.slots + [Slot(id="w1", function="worker", channel_id="source-a")],
        gates=legal_gates("source-a", "operator command"),
        human_override=True,
    )
    assert any(e.event == "human_override_who" for e in m.log)
