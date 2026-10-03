from taskorg.factory import element_at_rest
from taskorg.loop import _verifier_accepts
from taskorg.models import Artifact
from taskorg.seams import parse_seams


def test_parse_seams_tagged_only():
    picture = "Primary blocked. seam:source-a=independent_a seam:source-b=independent_b"
    seams = parse_seams(picture)
    assert [s.channel_id for s in seams] == ["source-a", "source-b"]
    assert parse_seams("no seams here") == []


def _art(claim, evidence, channel="verify"):
    return Artifact(claim=claim, evidence=evidence, uncertainty="n", channel_id=channel, delta_to_picture="x")


def test_verifier_requires_each_criterion_in_the_product():
    m = element_at_rest("v1", "Clear", "Deny", "Held")
    thin = _art("did a thing", ["none"], channel="head-integrate")
    assert _verifier_accepts(_art("PASS looking good", ["none"]), m, thin) is False
    full = _art("default task done", ["purpose held"], channel="head-integrate")
    assert _verifier_accepts(_art("PASS", []), m, full) is True


def test_verifier_cannot_vouch_by_echoing_criteria():
    m = element_at_rest("v2", "Clear", "Deny", "Held")
    empty_product = _art("lorem ipsum", [], channel="head-integrate")
    echo = _art("PASS", list(m.picture.success_criteria))
    assert _verifier_accepts(echo, m, empty_product) is False
    assert m.last_verify["misses"] == m.picture.success_criteria


def test_no_product_never_passes():
    m = element_at_rest("v3", "Clear", "Deny", "Held")
    assert _verifier_accepts(_art("PASS", ["default task", "purpose"]), m) is False
