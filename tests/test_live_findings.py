"""Findings from the first live pilot on Claude, Haiku 5.5, 27 October 2026 (docs/LIVE_TESTS.md).

1. The model put the answer in a key of its own ("ANSWER": "4.5%"), which the schema refuses, and did it
   again on the retry: nothing said that claim is the product.
2. After a rework, the verifier saw the old product in working memory and the new one under BRIEF, and
   failed right answers because "the ANSWER line appears only in the brief".
3. The harness asked for "one line ANSWER:", which the verifier read as a line of its own, though grading
   takes the marker at the end of a sentence; and the notes named quarters by month without saying which
   months make FY2026 Q1, which a careful reader is right to doubt.
4. Claude counted 1.39 to 1.73 times the tokens Genet estimated, so the size check undercounted.

From the rerun with those fixed: the lead wrote proposals as prose, and the kernel split them on spaces,
so each worker got the first word of its note; and it copied the <channel> placeholder of the plan
prompt literally, or left the channel empty.
"""

import math
from pathlib import Path

from taskorg.adapters import Brief, ModelAdapter
from taskorg.anthropic_live import TOKEN_RATIO, AnthropicAdapter
from taskorg.budget import Budget
from taskorg.compare import CONTEXT, DECOMPOSE_BRIEF, DONE_WHEN, PURPOSE, STRATEGIES, comparison_budget
from taskorg.factory import new_run
from taskorg.live import LiveAdapter, system_prompt
from taskorg.loop import PLAN_BRIEF, RETRY_NOTE, Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact, Status
from taskorg.subtasks import parse_proposals
from taskorg.suite import extract_answer
from taskorg.tools import Toolbox


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


# --- from the rerun with the fixes: proposals written as prose ---

def test_a_proposal_keeps_its_whole_note():
    [s] = parse_proposals(["subtask:orbrook@retrieve=Open orbrook.md, find the FY2026 Q1 revenue"])
    assert (s.channel_id, s.skill, s.named_failure) == ("orbrook", "retrieve", "Open orbrook.md, find the FY2026 Q1 revenue")


def test_proposals_are_cut_at_each_mark_and_nowhere_else():
    found = parse_proposals(["Two parts. subtask:a@retrieve=read a.md subtask:b=prior_year_mixed_in", "notsubtask:c=x", "subtask:=no channel"])
    assert [(s.channel_id, s.named_failure) for s in found] == [("a", "read a.md"), ("b", "prior year mixed in")]


class ByRole(ModelAdapter):
    name = "by-role"

    def __init__(self, plan):
        self.plan, self.briefs = plan, []

    def act(self, brief):
        self.briefs.append(brief)
        if brief.slot_function == "lead" and brief.mode == "plan":
            return _art("two parts", self.plan)
        if brief.slot_function == "verifier":
            return _art("PASS: ends with ANSWER: 5")
        if brief.slot_function == "worker":
            return _art(f"{brief.channel_id}: 5")
        return _art("total 5. ANSWER: 5")


def test_a_crew_worker_gets_the_leads_whole_note(tmp_path: Path):
    m = new_run("crew-1", "What is the total?", "answer from the notes", "ends with ANSWER:")
    m.state.success_criteria = ["ANSWER:"]
    adapter = ByRole(["subtask:alpha@retrieve=Open alpha.md, report its Q1 revenue",
                      "subtask:beta@retrieve=Open beta.md, report its Q1 revenue"])
    engine = STRATEGIES["always"](MemoryStore(tmp_path), adapter=adapter, budget=comparison_budget(),
                                  toolbox=Toolbox(roots=[tmp_path]))
    engine.run_task(m, context="c", operator_question="?")
    notes = sorted(b.packet.rsplit("Lead's note for this sub-agent: ", 1)[1] for b in adapter.briefs if b.slot_function == "worker")
    assert notes == ["Open alpha.md, report its Q1 revenue", "Open beta.md, report its Q1 revenue"]


def test_the_plan_prompts_show_a_real_proposal_not_placeholders():
    for brief in (PLAN_BRIEF, DECOMPOSE_BRIEF):
        assert "<" not in brief and "for example subtask:" in brief
        assert "that file's name without its extension" in brief
