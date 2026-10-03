from taskorg.factory import new_run
from taskorg.loop import _verifier_accepts
from taskorg.models import Artifact
from taskorg.subtasks import parse_subtasks


def test_parse_subtasks_tagged_only():
    context = "Primary blocked. subtask:source-a=independent_a subtask:source-b=independent_b"
    subtasks = parse_subtasks(context)
    assert [s.channel_id for s in subtasks] == ["source-a", "source-b"]
    assert parse_subtasks("no subtasks here") == []


def _art(claim, evidence, channel="verify"):
    return Artifact(claim=claim, evidence=evidence, uncertainty="n", channel_id=channel, context_update="x")


def test_verifier_requires_each_criterion_in_the_product():
    m = new_run("v1", "Summarize the notes", "Keep sources apart", "Summary written")
    thin = _art("did a thing", ["none"], channel="lead-merge")
    assert _verifier_accepts(_art("PASS looking good", ["none"]), m, thin) is False
    full = _art("default task done", ["purpose held"], channel="lead-merge")
    assert _verifier_accepts(_art("PASS", []), m, full) is True


def test_verifier_cannot_vouch_by_echoing_criteria():
    m = new_run("v2", "Summarize the notes", "Keep sources apart", "Summary written")
    empty_product = _art("lorem ipsum", [], channel="lead-merge")
    echo = _art("PASS", list(m.state.success_criteria))
    assert _verifier_accepts(echo, m, empty_product) is False
    assert m.last_verify["misses"] == m.state.success_criteria


def test_no_product_never_passes():
    m = new_run("v3", "Summarize the notes", "Keep sources apart", "Summary written")
    assert _verifier_accepts(_art("PASS", ["default task", "purpose"]), m) is False
