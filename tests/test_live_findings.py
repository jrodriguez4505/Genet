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

From the second rerun: the verifier read the product's claim but not the evidence given with it, and
failed sourced answers as unsourced.

From sizing a tight-context run on the tapes: Haiku read each file and also searched it, so a call
carried 2.4 times the text of the files it read (up to 3.8), and the gates measured files at four
characters a token while Claude counts about 1.5 times that. A call ran about 3.5 times what the gates
judged, so they would keep work in one call that then overflowed.

From the tight-context run (4,000 tokens a call): the gates split the right tasks, but each sub-agent,
given the whole goal and a note that said why its part was separate, read every company's file and not
only its own, and overran the call its part was sized for.

From the rerun with sub-agents scoped: the lead, not told how much one call holds, proposed no
sub-agents for work that could not fit; and Haiku's replies ran to 1,600 tokens, so the room kept for
the next reply left no room for its brief.
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
from taskorg.tools import READ_CAP, Toolbox


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


# --- from the second rerun: the verifier reads the evidence too ---


def _verify_packet(tmp_path: Path, evidence: list[str]) -> str:
    m = new_run("evidence-1", "What was Orbrook's FY2026 Q1 revenue?", "answer from the notes", "ends with ANSWER:")
    m.state.success_criteria = ["ANSWER:"]
    product = Artifact(claim="Revenue was 36.9. ANSWER: 36.9", evidence=evidence, uncertainty="", channel_id="c",
                       context_update="", requests=[])
    adapter = Replies(_art("plan"), product, _art("PASS: sourced and ends with ANSWER: 36.9"))
    Engine(MemoryStore(tmp_path), adapter=adapter, budget=comparison_budget()).run_task(m, context="c", operator_question="?")
    return next(b.packet for b in adapter.briefs if b.slot_function == "verifier")


def test_the_verifier_reads_the_evidence_given_with_the_product(tmp_path: Path):
    packet = _verify_packet(tmp_path, ['orbrook.md:3: "Revenue for the January-March quarter reached $36.9 million."'])
    product = packet.split("PRODUCT UNDER REVIEW", 1)[1].split("VERIFIER RULE", 1)[0]
    assert "ANSWER: 36.9" in product and "EVIDENCE GIVEN WITH IT\n- orbrook.md:3:" in product


def test_a_product_with_no_evidence_shows_none(tmp_path: Path):
    assert "EVIDENCE GIVEN WITH IT" not in _verify_packet(tmp_path, [])


def test_the_evidence_the_verifier_reads_is_bounded(tmp_path: Path):
    packet = _verify_packet(tmp_path, [f"line {i} " + "x" * 1000 for i in range(20)])
    shown = [ln for ln in packet.splitlines() if ln.startswith("- line ")]
    assert len(shown) == 12 and max(len(ln) for ln in shown) <= 2 + 400
    assert "[8 more not shown]" in packet


# --- from sizing the tight-context run: one copy of each file per call, in the model's tokens ---


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "alpha.md").write_text("alpha revenue Q1 5\nalpha churn Q1 2\n")
    (root / "beta.md").write_text("beta revenue Q1 7\n")
    return root


def test_a_file_read_in_full_is_not_copied_again(tmp_path: Path):
    tb, have = Toolbox(roots=[_workspace(tmp_path)]), set()
    assert tb.run("read:alpha.md", have).startswith("[read alpha.md]\nalpha revenue")
    assert tb.run("read:alpha.md", have) == "[read alpha.md] already in full above"
    found = tb.run("retrieve:revenue", have)
    assert "beta.md:1:" in found and "alpha.md" not in found.split("\n[")[0]
    assert "[1 file(s) read in full above not searched again]" in found


def test_a_truncated_read_leaves_the_rest_searchable(tmp_path: Path):
    root = _workspace(tmp_path)
    (root / "long.md").write_text("x " * READ_CAP + "\nlong revenue Q1 9\n")
    tb, have = Toolbox(roots=[root]), set()
    assert "[truncated at" in tb.run("read:long.md", have)
    assert "long.md:2:" in tb.run("retrieve:long revenue", have)


def test_reads_run_first_so_a_search_beside_them_skips_what_they_return(tmp_path: Path):
    m = new_run("one-copy-1", "What was alpha's Q1 revenue?", "answer from the notes", "ends with ANSWER:")
    m.state.success_criteria = ["ANSWER:"]
    adapter = Replies(_art("one agent is enough"), _art("looking", ["retrieve:alpha revenue", "read:alpha.md"]),
                      _art("alpha 5. ANSWER: 5"), _art("PASS: ANSWER: 5"))
    Engine(MemoryStore(tmp_path), adapter=adapter, budget=comparison_budget(),
           toolbox=Toolbox(roots=[_workspace(tmp_path)])).run_task(m, context="c", operator_question="?")
    results = adapter.briefs[2].packet.split("TOOL RESULTS", 1)[1]
    assert results.index("[read alpha.md]") < results.index("[retrieve alpha revenue]")
    assert results.count("alpha revenue Q1 5") == 1


def test_the_gates_measure_files_in_the_models_tokens(tmp_path: Path):
    root = _workspace(tmp_path)
    plain = Engine(MemoryStore(tmp_path / "a"), adapter=Replies(), toolbox=Toolbox(roots=[root]))
    claude = Engine(MemoryStore(tmp_path / "b"), adapter=AnthropicAdapter("", "claude-haiku-5-5", client=object()),
                    toolbox=Toolbox(roots=[root]))
    sub = parse_proposals(["subtask:alpha@retrieve=read alpha.md"])[0]
    [chars4] = plain._material(sub).values()
    [scaled] = claude._material(sub).values()
    assert scaled == math.ceil(chars4 * TOKEN_RATIO) and scaled > chars4


# --- from the tight-context run: a sub-agent's tools open only its part ---


def test_a_scoped_toolbox_opens_only_its_files(tmp_path: Path):
    root = _workspace(tmp_path)
    tb = Toolbox(roots=[root]).scoped([root / "alpha.md"])
    assert tb.read("alpha.md").startswith("[read alpha.md]")
    assert tb.read("beta.md") == "[read beta.md] not found in the workspace"
    assert "beta.md" not in tb.retrieve("revenue") and "alpha.md:1:" in tb.retrieve("revenue")
    assert tb.observe().splitlines()[1:] == ["alpha.md"]


class Reader(ByRole):
    """Workers that try to read every file, as Haiku's did."""

    def act(self, brief):
        if brief.slot_function == "worker" and "TOOL RESULTS" not in brief.packet:
            self.briefs.append(brief)
            return _art("reading", ["read:alpha.md", "read:beta.md"])
        return super().act(brief)


def test_a_sub_agent_reads_only_the_files_measured_for_its_part(tmp_path: Path):
    m = new_run("scoped-1", "What is the total?", "answer from the notes", "ends with ANSWER:")
    m.state.success_criteria = ["ANSWER:"]
    adapter = Reader(["subtask:alpha@retrieve=report alpha's revenue", "subtask:beta@retrieve=report beta's revenue"])
    engine = STRATEGIES["always"](MemoryStore(tmp_path), adapter=adapter, budget=comparison_budget(),
                                  toolbox=Toolbox(roots=[_workspace(tmp_path)]))
    engine.run_task(m, context="c", operator_question="?")
    after = {b.channel_id: b.packet.split("TOOL RESULTS", 1)[1] for b in adapter.briefs
             if b.slot_function == "worker" and "TOOL RESULTS" in b.packet}
    assert "alpha revenue Q1 5" in after["alpha"] and "[read beta.md] not found in the workspace" in after["alpha"]
    assert "beta revenue Q1 7" in after["beta"] and "[read alpha.md] not found in the workspace" in after["beta"]
    first = next(b.packet for b in adapter.briefs if b.slot_function == "worker" and b.channel_id == "alpha")
    assert "Your files: alpha.md; your tools open only these." in first and "the lead combines them" in first


def test_a_part_with_no_measured_files_keeps_the_whole_workspace(tmp_path: Path):
    m = new_run("scoped-2", "What is the total?", "answer from the notes", "ends with ANSWER:")
    m.state.success_criteria = ["ANSWER:"]
    adapter = Reader(["subtask:east@retrieve=report the east figures", "subtask:west@retrieve=report the west figures"])
    engine = STRATEGIES["always"](MemoryStore(tmp_path), adapter=adapter, budget=comparison_budget(),
                                  toolbox=Toolbox(roots=[_workspace(tmp_path)]))
    engine.run_task(m, context="c", operator_question="?")
    after = [b.packet for b in adapter.briefs if b.slot_function == "worker" and "TOOL RESULTS" in b.packet]
    assert after and all("beta revenue Q1 7" in p and "alpha revenue Q1 5" in p for p in after)


# --- from the scoped rerun: the lead plans knowing the limit, and replies are brief ---


def _plan_packet(tmp_path: Path, adapter, toolbox, budget):
    m = new_run("size-1", "What is the total?", "answer from the notes", "ends with ANSWER:")
    m.state.success_criteria = ["ANSWER:"]
    seen = []

    def act(brief):
        seen.append(brief)
        if brief.mode == "plan":
            return _art("one agent is enough")
        if brief.slot_function == "verifier":
            return _art("PASS: ANSWER: 5")
        return _art("total 5. ANSWER: 5")
    adapter.act = act
    Engine(MemoryStore(tmp_path), adapter=adapter, budget=budget, toolbox=toolbox).run_task(m, context="c", operator_question="?")
    return next(b.packet for b in seen if b.mode == "plan")


def test_the_lead_plans_knowing_what_one_call_holds(tmp_path: Path):
    packet = _plan_packet(tmp_path, Replies(), Toolbox(roots=[_workspace(tmp_path)]), comparison_budget(40, 4000))
    assert "SIZE. One call holds at most 4,000 tokens in all" in packet
    assert "The workspace has 2 file(s) of about 4 to 9 tokens each." in packet


def test_the_file_sizes_are_in_the_models_tokens(tmp_path: Path):
    claude = AnthropicAdapter("", "claude-haiku-5-5", client=object())
    packet = _plan_packet(tmp_path, claude, Toolbox(roots=[_workspace(tmp_path)]), comparison_budget(40, 4000))
    assert f"of about {math.ceil(4 * TOKEN_RATIO)} to {math.ceil(9 * TOKEN_RATIO)} tokens each" in packet


def test_no_size_note_without_a_workspace(tmp_path: Path):
    assert "SIZE." not in _plan_packet(tmp_path, Replies(), Toolbox(), comparison_budget(40, 4000))


def test_replies_are_asked_to_be_brief():
    prompt = system_prompt(_brief())
    assert "evidence (array of strings): at most 5, each a short quote" in prompt
    assert "uncertainty (string): one sentence" in prompt and "Be brief" in prompt
