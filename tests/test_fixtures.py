"""Phase 0 fixtures. These must fail closed."""

import pytest

from taskorg.errors import InvariantError
from taskorg.factory import new_run
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


def test_worker_cannot_change_roster():
    m = new_run("fx-roster-guard", "complete the task", "keep the goal intact", "task finished")
    with pytest.raises(InvariantError) as e:
        m.set_roster("worker-rogue", m.state.slots + [Slot(id="w1", function="worker", channel_id="part-b")])
    assert e.value.code == "INV-1"


def test_worker_cannot_spawn():
    m = new_run("fx-spawn", "complete the task", "keep the goal intact", "task finished")
    with pytest.raises(InvariantError) as e:
        m.worker_spawn("worker-1", Slot(id="w2", function="worker", channel_id="part-a"))
    assert e.value.code == "INV-2"


def test_reviewer_cannot_take_over():
    m = new_run("fx-reviewer-guard", "complete the task", "keep the goal intact", "task finished")
    m.open_review("cheaper failure: the first source is stale", "n1")
    with pytest.raises(InvariantError) as e:
        m.reviewer_take_over("n1")
    assert e.value.code == "REVIEW"


def test_reviewer_cannot_halt():
    m = new_run("fx-reviewer-halt", "complete the task", "keep the goal intact", "task finished")
    with pytest.raises(InvariantError) as e:
        m.reviewer_halt()
    assert e.value.code == "REVIEW"


def test_complete_with_open_note_fails():
    m = new_run("fx-open-note", "complete the task", "keep the goal intact", "task finished")
    m.open_review("why this source and not source-a", "n1")
    with pytest.raises(InvariantError) as e:
        m.complete()
    assert e.value.code == "INV-4"


def test_defer_then_complete_ok():
    m = new_run("fx-defer", "complete the task", "keep the goal intact", "task finished")
    m.open_review("later", "n1")
    m.answer_review("lead-1", "n1", "DEFER", "hold until the context is checked")
    m.complete()
    assert m.status.value == "complete"


def test_split_without_failure_refused():
    m = new_run("fx-no-failure", "complete the task", "keep the goal intact", "task finished")
    bad = GateRecord(
        can_someone_else=False,
        should_we=False,
        named_failure=None,
        could_we=True,
        channel_id="part-b",
    )
    with pytest.raises(InvariantError) as e:
        m.set_roster(
            "lead-1",
            m.state.slots + [Slot(id="w1", function="worker", channel_id="part-b")],
            gates=bad,
        )
    assert e.value.code == "INV-8"


def test_gate_order_violation_refused():
    m = new_run("fx-gate-order", "complete the task", "keep the goal intact", "task finished")
    bad = GateRecord(
        can_someone_else=False,
        should_we=True,
        named_failure="context overflow",
        could_we=True,
        channel_id="part-b",
        order=("could_we", "should_we", "can_someone_else"),
    )
    with pytest.raises(InvariantError) as e:
        m.set_roster(
            "lead-1",
            m.state.slots + [Slot(id="w1", function="worker", channel_id="part-b")],
            gates=bad,
        )
    assert e.value.code == "INV-9"


def test_can_someone_else_blocks_spawn():
    m = new_run("fx-someone-else", "complete the task", "keep the goal intact", "task finished")
    bad = GateRecord(
        can_someone_else=True,
        should_we=True,
        named_failure="want another body",
        could_we=True,
        channel_id="part-b",
    )
    with pytest.raises(InvariantError) as e:
        m.set_roster(
            "lead-1",
            m.state.slots + [Slot(id="w1", function="worker", channel_id="part-b")],
            gates=bad,
        )
    assert e.value.code == "GATE-1"


def test_exploratory_spawn_when_we_can_see_fails():
    m = new_run("fx-explore", "complete the task", "keep the goal intact", "task finished")
    m.update_context("lead-1", "second source visible, two subtasks")
    with pytest.raises(InvariantError) as e:
        m.request_exploratory_spawn(
            "lead-1",
            Slot(id="w-explore", function="worker", skill="observe", channel_id="explore"),
            legal_gates("explore", "need a look"),
        )
    assert e.value.code == "INV-10"


def test_exploratory_spawn_when_observe_skill_exists_fails():
    m = new_run("fx-observe-exists", "complete the task", "keep the goal intact", "task finished")
    m.switch_skill("lead-1", "lead-1", "observe", "observe from here")
    with pytest.raises(InvariantError) as e:
        m.request_exploratory_spawn(
            "lead-1",
            Slot(id="w-explore", function="worker", skill="observe", channel_id="explore"),
            legal_gates("explore"),
        )
    assert e.value.code == "INV-10"


def test_switch_skill_is_not_a_new_identity():
    m = new_run("fx-switch_skill", "complete the task", "keep the goal intact", "task finished")
    m.switch_skill("lead-1", "lead-1", "retrieve", "pull the index")
    assert m.state.slot("lead-1").function == "lead"
    assert m.state.slot("lead-1").skill == "retrieve"
    assert m.state.worker_count() == 0


def test_legal_split_after_context_and_gates():
    m = new_run("fx-legal-split", "complete the task", "keep the goal intact", "task finished")
    m.update_context("lead-1", "primary path blocked; two sources are open")
    m.switch_skill("lead-1", "lead-1", "reason", "pick How")
    m.set_method("lead-1", "multi-axis", ["parallel", "reverse", "fan_in"])
    gates = legal_gates("source-b", "independent source-b channel")
    m.set_roster(
        "lead-1",
        m.state.slots + [Slot(id="w-source-b", function="worker", skill="execute", channel_id="source-b")],
        gates=gates,
    )
    m.accept_artifact(
        Artifact(
            claim="source-b checked through section two",
            evidence=["observe the index"],
            uncertainty="two sections not yet read",
            channel_id="source-b",
            context_update="source-b held",
        )
    )
    m.open_review("why not skip the first source entirely", "n1")
    m.answer_review("lead-1", "n1", "CHANGE_METHOD", "hold multi-axis")
    m.complete()
    s = m.summary()
    assert s["workers"] == 1
    assert s["could_this_have_been_one"] is False
    assert s["context_checked"] is True
    assert "fan_in" in s["axes"]


def test_single_agent_complete_could_have_been_one():
    m = new_run("fx-one", "write the report", "shared context", "report written")
    m.update_context("lead-1", "context is enough to write")
    m.complete()
    assert m.summary()["could_this_have_been_one"] is True


def test_verifier_cannot_pass_failed_stop():
    m = new_run("fx-stop", "complete the task", "keep the goal intact", "task finished")
    m.mark_stop_rule_failed("success_criteria[0]")
    with pytest.raises(InvariantError) as e:
        m.verifier_pass_with_failed_stop()
    assert e.value.code == "INV-5"
    with pytest.raises(InvariantError):
        m.complete()


def test_memory_cannot_dump():
    m = new_run("fx-dump", "complete the task", "keep the goal intact", "task finished")
    with pytest.raises(InvariantError) as e:
        m.dump_unscoped_history_into_brief()
    assert e.value.code == "INV-6"


def test_cue_requires_expiry():
    m = new_run("fx-cue", "complete the task", "keep the goal intact", "task finished")
    with pytest.raises(InvariantError):
        m.mint_cue(Cue(id="c1", trigger="rework twice", payload="method exhausted", target="lead-1", expiry=""))
    m.mint_cue(Cue(id="c1", trigger="rework twice", payload="method exhausted", target="lead-1", expiry="run-end"))
    assert "c1" in m.cues


def test_human_override_is_logged():
    m = new_run("fx-human", "complete the task", "keep the goal intact", "task finished")
    m.set_roster(
        "operator",
        m.state.slots + [Slot(id="w1", function="worker", channel_id="source-a")],
        gates=legal_gates("source-a", "operator command"),
        human_override=True,
    )
    assert any(e.event == "human_override_roster" for e in m.log)
