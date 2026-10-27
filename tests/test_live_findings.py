"""Findings from the first live pilot on Claude, Haiku 5.5, 27 October 2026 (docs/LIVE_TESTS.md).

1. The model put the answer in a key of its own ("ANSWER": "4.5%"), which the schema refuses, and did it
   again on the retry: nothing said that claim is the product.
2. After a rework, the verifier saw the old product in working memory and the new one under BRIEF, and
   failed right answers because "the ANSWER line appears only in the brief".
3. The harness asked for "one line ANSWER:", which the verifier read as a line of its own, though grading
   takes the marker at the end of a sentence; and the notes named quarters by month without saying which
   months make FY2026 Q1, which a careful reader is right to doubt.
4. Claude counted 1.39 to 1.73 times the tokens Genet estimated, so the size check undercounted.
"""

import math
from pathlib import Path

from taskorg.adapters import Brief, ModelAdapter
from taskorg.anthropic_live import TOKEN_RATIO, AnthropicAdapter
from taskorg.budget import Budget
from taskorg.compare import CONTEXT, DONE_WHEN, PURPOSE
from taskorg.factory import new_run
from taskorg.live import LiveAdapter, system_prompt
from taskorg.loop import RETRY_NOTE, Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact, Status
from taskorg.suite import extract_answer


def _art(claim, requests=()):
    return Artifact(claim=claim, evidence=[], uncertainty="", channel_id="c", context_update="", requests=list(requests))


class Replies(ModelAdapter):
    name = "replies"

    def __init__(self, *replies):
        self.replies, self.briefs = list(replies), []

    def act(self, brief):
        self.briefs.append(brief)
        return self.replies.pop(0)


def _brief(function="lead"):
    return Brief(function, "draft", "p", "g", "u", "c", "d")


def test_the_prompt_says_claim_is_the_product_and_other_keys_are_refused():
    prompt = system_prompt(_brief())
    assert "claim (string): your product, all of it" in prompt
    assert "a reply with any other key is refused, so what it would hold goes in claim" in prompt
    assert "what it held belongs in claim, which is the product" in RETRY_NOTE


def test_the_verifier_judges_the_reworked_product_and_only_that(tmp_path: Path):
    m = new_run("rework-1", "What was Orbrook's FY2026 Q1 revenue?", "answer from the notes", "ends with ANSWER:")
    m.state.success_criteria = ["ANSWER:"]
    adapter = Replies(
        _art("plan"),                                          # lead plans: one agent is enough
        _art("first product: revenue was 36.9"),               # no ANSWER marker
        _art("FAIL: no ANSWER marker"),
        _art("second product: revenue was 36.9. ANSWER: 36.9"),
        _art("PASS: ends with ANSWER: 36.9"),
    )
    result = Engine(MemoryStore(tmp_path), adapter=adapter, budget=Budget.for_tier("normal")).run_task(
        m, context="c", operator_question="?")
    assert result.verified and m.status == Status.COMPLETE
    first, second = [b.packet for b in adapter.briefs if b.slot_function == "verifier"]
    assert "PRODUCT UNDER REVIEW" in first and "first product" in first
    assert "PRODUCT UNDER REVIEW" in second and "second product" in second
    assert "first product" not in second  # working memory holds the reworked product too


def test_the_harness_asks_for_what_grading_accepts():
    for text in (PURPOSE, DONE_WHEN):
        assert "ANSWER: <value>" in text and "one line" not in text
    assert extract_answer("Orbrook's Q1 revenue was $36.9 million. ANSWER: 36.9") == "36.9"


def test_the_harness_says_which_months_make_each_quarter():
    for q, months in (("Q1", "January to March"), ("Q2", "April to June"), ("Q3", "July to September"),
                      ("Q4", "October to December")):
        assert f"{q} is {months}" in CONTEXT or f"{q} {months}" in CONTEXT


def test_the_claude_size_estimate_does_not_undercount():
    b = _brief()
    b.packet = "x" * 3000
    plain = LiveAdapter("https://endpoint.invalid", "k", "m").estimate_tokens(b)
    claude = AnthropicAdapter("", "claude-haiku-5-5", client=object()).estimate_tokens(b)
    assert TOKEN_RATIO >= 1.73  # the most the pilot measured
    assert claude == math.ceil(plain * TOKEN_RATIO)
