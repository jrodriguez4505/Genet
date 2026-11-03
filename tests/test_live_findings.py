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
from dataclasses import replace
from pathlib import Path

import pytest

from taskorg.adapters import Brief, ModelAdapter
from taskorg.anthropic_live import TOKEN_RATIO, AnthropicAdapter
from taskorg.budget import Budget
from taskorg.compare import CONTEXT, DECOMPOSE_BRIEF, DONE_WHEN, PURPOSE, STRATEGIES, comparison_budget, run_trial
from taskorg.factory import new_run
from taskorg.live import LiveAdapter, system_prompt
from taskorg.loop import PLAN_BRIEF, RETRY_NOTE, Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact, Status
from taskorg.sim import SimModel
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


def _plan_packet(tmp_path: Path, adapter, toolbox, budget, goal="What is the total?"):
    m = new_run("size-1", goal, "answer from the notes", "ends with ANSWER:")
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


def test_a_lead_is_told_what_the_goals_files_come_to_only_when_they_do_not_fit_a_call(tmp_path: Path):
    """On 2 November half the leads did the sum wrong from a range of sizes, proposed nothing and overflowed."""
    root = tmp_path / "w"
    root.mkdir()
    for name in ("north", "south", "east"):
        (root / f"{name}.md").write_text("Revenue line. " * 200)  # 700 tokens each
    box = Toolbox(roots=[root])
    goal = "What was the revenue of North and South?"
    claude = AnthropicAdapter("", "claude-haiku-5-5", client=object())
    short = _plan_packet(tmp_path / "a", claude, box, comparison_budget(40, 3_000), goal=goal)
    assert f"The 2 files the goal names come to about {2 * math.ceil(700 * TOKEN_RATIO):,} tokens" in short
    assert "they do not fit one call" in short
    roomy = _plan_packet(tmp_path / "b", Replies(), box, comparison_budget(40, 200_000), goal=goal)
    assert "files the goal names" not in roomy
    # One named file: a split could not help. None named: the kernel has nothing to add up.
    one = _plan_packet(tmp_path / "c", Replies(), box, comparison_budget(40, 1_000), goal="What was North's revenue?")
    none = _plan_packet(tmp_path / "d", Replies(), box, comparison_budget(40, 1_000))
    assert "files the goal names" not in one and "files the goal names" not in none


def test_a_lead_is_told_how_to_name_a_group_only_when_the_workspace_does_not_fit_a_call(tmp_path: Path):
    """On 2 November a lead told the limit proposed groups of files, and the gates refused them all as unknown
    material. The note costs tokens, and changes the request, so a roomy run neither pays for it nor differs."""
    root = tmp_path / "w"
    root.mkdir()
    for name in ("north", "south", "east"):
        (root / f"{name}.md").write_text("Revenue line. " * 400)
    tight = _plan_packet(tmp_path / "tight", Replies(), Toolbox(roots=[root]), comparison_budget(40, 2_000))
    roomy = _plan_packet(tmp_path / "roomy", Replies(), Toolbox(roots=[root]), comparison_budget(40, 200_000))
    assert "name each file in NAMED_FAILURE" in tight and "at most 4 sub-agents" in tight
    assert "SIZE." in roomy and "NAMED_FAILURE, for example subtask:north-group" not in roomy


def _crew_plan_packet(tmp_path: Path, strategy: str, cap: int) -> str:
    from taskorg.suite import build_suite

    suite = build_suite(seed=7, per_family=1, families=("aggregate",), entities=10, distractors=6)
    root = suite.write_corpus(tmp_path / f"corpus-{strategy}-{cap}")
    claude = AnthropicAdapter("", "claude-haiku-5-5", client=object())
    seen = []

    def act(brief):
        seen.append(brief)
        return _art("PASS ANSWER: 1")
    claude.act = act
    run_trial(suite.tasks[0], strategy, claude, root, budget=comparison_budget(40, cap), tool_rounds=4)
    return next(b.packet for b in seen if b.mode == "plan")


def test_the_told_crew_gets_the_same_size_notes_in_its_own_words(tmp_path: Path):
    """A comparison where only one lead is told what fits measures the notes as well as the staffing."""
    told = _crew_plan_packet(tmp_path, "always-told", 8_000)
    assert "SIZE. One call holds at most 8,000 tokens" in told and "The 10 files the goal names come to about" in told
    assert "at most 4 workers" in told and "name each file in WHAT_THE_WORKER_DOES" in told and "NAMED_FAILURE" not in told
    # The plain crew's request is what its tapes hold, and a roomy told crew has nothing to be told about fit.
    plain = _crew_plan_packet(tmp_path, "always", 8_000)
    assert "SIZE." not in plain and "name each file" not in plain
    roomy = _crew_plan_packet(tmp_path, "always-told", 200_000)
    assert "SIZE. One call holds at most 200,000 tokens" in roomy and "name each file" not in roomy and "files the goal names" not in roomy


def test_the_told_crew_still_has_no_gates(tmp_path: Path):
    from taskorg.sim import SimModel
    from taskorg.suite import build_suite, slug

    suite = build_suite(seed=7, per_family=1, families=("aggregate",), entities=10, distractors=6)
    task = suite.tasks[0]
    files = [f"{slug(e)}.md" for e in task.entities]
    root = suite.write_corpus(tmp_path / "corpus")

    class Groups(SimModel):
        def act(self, brief):
            art = super().act(brief)
            if brief.mode == "plan":
                art.requests = [f"subtask:group-a@retrieve=report {' '.join(files[:5])}", f"subtask:group-b@retrieve=report {' '.join(files[5:])}"]
            return art

    # At a roomy cap the gates would keep this single; a crew staffs what it proposes.
    r = run_trial(task, "always-told", Groups(), root, budget=comparison_budget(40, 200_000), tool_rounds=4)
    assert r.workers == 2 and r.status == "complete" and r.answer_right
    assert run_trial(task, "genet", Groups(), root, budget=comparison_budget(40, 200_000), tool_rounds=4).workers == 0


def test_a_grouped_plan_runs_end_to_end_on_the_sim(tmp_path: Path):
    """The rehearsal for the live run: a lead that plans as Haiku did, in groups, with the files named."""
    from taskorg.sim import SimModel
    from taskorg.suite import build_suite, slug

    suite = build_suite(seed=7, per_family=1, families=("aggregate",), entities=10, distractors=6)
    task = suite.tasks[0]
    files = [f"{slug(e)}.md" for e in task.entities]
    root = suite.write_corpus(tmp_path / "corpus")

    class Groups(SimModel):
        def act(self, brief):
            art = super().act(brief)
            if brief.mode == "plan":
                art.requests = [f"subtask:group-a@retrieve=figures_get_mixed {' '.join(files[:5])}",
                                f"subtask:group-b@retrieve=figures_get_mixed {' '.join(files[5:])}"]
            return art

    r = run_trial(task, "genet", Groups(), root, budget=comparison_budget(40, 4_000), tool_rounds=4)
    assert r.workers == 2 and r.refused == 0 and r.status == "complete" and r.answer_right


def test_a_group_that_names_its_files_passes_the_gates_and_opens_only_those(tmp_path: Path):
    from taskorg.gates import assess

    root = tmp_path / "w"
    root.mkdir()
    for name in ("north", "south", "east", "west"):
        (root / f"{name}.md").write_text(f"# {name}\n" + "Revenue line. " * 400)
    props = parse_proposals(["subtask:north-group@retrieve=regions_get_mixed north.md south.md",
                             "subtask:east-group@retrieve=regions_get_mixed east.md west.md",
                             "subtask:unnamed@retrieve=regions_get_mixed"])
    box = Toolbox(roots=[root])
    assert sorted(Path(p).name for p in box.material(props[0].channel_id, props[0].named_failure)) == ["north.md", "south.md"]
    assert box.material(props[2].channel_id, props[2].named_failure) is None
    named = props[:2]
    v = assess(named, policy="measured", material=lambda s: box.material(s.channel_id, s.named_failure),
               context_limit=3_000, overhead=500)
    assert [a.legal for a in v] == [True, True] and {a.basis for a in v} == {"measured"}
    # A group that names nothing goes to the lead, and the groups that can be measured are judged alone.
    v = assess(props, policy="measured", material=lambda s: box.material(s.channel_id, s.named_failure),
               context_limit=3_000, overhead=500)
    assert [a.legal for a in v] == [True, True, False] and v[2].gate == "should_we" and "material is unknown" in v[2].refused
    scope = box.scoped(box.material(props[0].channel_id, props[0].named_failure))
    assert "Revenue" in scope.read("north.md") and "Revenue" not in scope.read("east.md")


def _names(tmp_path: Path, *files: str) -> Toolbox:
    root = tmp_path / "names"
    root.mkdir()
    for name in files:
        (root / name).write_text("Revenue line. " * 20)
    return Toolbox(roots=[root])


@pytest.mark.parametrize("note, expected", [
    # What Haiku wrote on 2 November, for files named with hyphens.
    ("figures mixed everholt.md cobalt ridge.md hollis arcade.md", ["cobalt-ridge.md", "everholt.md", "hollis-arcade.md"]),
    ("figures mixed Quillon Bio.md, Cobalt Ridge.md", ["cobalt-ridge.md", "quillon-bio.md"]),
    # And run together, from a brief whose only example was a one-word name.
    ("figures mixed cobaltridge.md hollisarcade.md everholt.md", ["cobalt-ridge.md", "everholt.md", "hollis-arcade.md"]),
    ("read quillonbio.md", ["quillon-bio.md"]),
    # Underscores in a note read as spaces, so a name with one arrives spaced.
    ("figures mixed q3 report.md", ["q3_report.md"]),
    # The look-alike whose name holds the other's: the longest wins, and each is told apart.
    ("read quillon bio.md", ["quillon-bio.md"]),
    ("read bio.md", ["bio.md"]),
    ("read quillon bio.md bio.md", ["bio.md", "quillon-bio.md"]),
    # Prose that mentions a company names no file, and neither does another extension.
    ("cobalt ridge and everholt figures get mixed", None),
    ("figures mixed cobalt ridge.txt", None),
    ("about 4.5 percent, e.g. the Cobalt Ridge figures", None),
])
def test_a_note_names_a_file_however_a_model_spelled_it(tmp_path: Path, note, expected):
    box = _names(tmp_path, "everholt.md", "cobalt-ridge.md", "hollis-arcade.md", "quillon-bio.md", "bio.md", "q3_report.md")
    found = box.material("group-a", note)
    assert (sorted(Path(p).name for p in found) if found else None) == expected


def test_a_loose_name_stays_in_the_sandbox_and_a_long_note_stays_cheap(tmp_path: Path):
    box = _names(tmp_path, "cobalt-ridge.md", ".hidden.md")
    assert box.material("x", "read hidden.md .hidden.md") is None
    outside = tmp_path / "outside.md"
    outside.write_text("secret")
    assert box.material("x", "read outside.md ../outside.md") is None
    assert box.material("x", "word " * 100_000 + "cobalt ridge.md") is None  # past NOTE_CAP
    assert sorted(Path(p).name for p in box.material("x", ".x " * 600 + "cobalt ridge.md")) == ["cobalt-ridge.md"]


def test_an_unmeasured_part_goes_to_the_lead_and_the_plan_survives(tmp_path: Path):
    from taskorg.gates import LEAD_COVERS, Subtask, assess
    from taskorg.sim import SimModel
    from taskorg.suite import build_suite, slug

    sizes = {"a": {"a": 2_000}, "b": {"b": 2_000}, "c": None}
    parts = [Subtask(c, "keep apart", skill="retrieve") for c in sizes]
    v = assess(parts, policy="measured", material=lambda s: sizes[s.channel_id], context_limit=3_000, overhead=500)
    assert [a.legal for a in v] == [True, True, False] and [a.basis for a in v[:2]] == ["measured", "measured"]
    # One measured part is not a split. With none, the old refusal stands.
    v = assess(parts[1:], policy="measured", material=lambda s: sizes[s.channel_id], context_limit=1_000, overhead=500)
    assert not any(a.legal for a in v)
    assert all(a.refused.startswith("a split does not make the work fit") for a in v)
    v = assess(parts[1:], policy="measured", material=lambda s: sizes[s.channel_id], context_limit=4_000, overhead=500)
    assert not any(a.legal for a in v)
    sizes["b"] = None
    v = assess(parts[1:], policy="measured", material=lambda s: sizes[s.channel_id], context_limit=3_000, overhead=500)
    assert all("no measurable reason" in a.refused for a in v)
    assert LEAD_COVERS.startswith("one open sub-task")

    suite = build_suite(seed=7, per_family=1, families=("aggregate",), entities=10, distractors=6)
    task = suite.tasks[0]
    files = [f"{slug(e)}.md" for e in task.entities]
    root = suite.write_corpus(tmp_path / "corpus")

    class Guesses(SimModel):
        def act(self, brief):
            art = super().act(brief)
            if brief.mode == "plan":
                spaced = " ".join(f.replace("-", " ") for f in files[:4])
                art.requests = [f"subtask:group-a@retrieve=figures_get_mixed {spaced}",
                                f"subtask:group-b@retrieve=figures_get_mixed {' '.join(files[4:8])}",
                                "subtask:group-c@retrieve=figures_get_mixed the_other_two"]
            return art

    r = run_trial(task, "genet", Guesses(), root, budget=comparison_budget(40, 4_000), tool_rounds=4)
    assert r.workers == 2 and r.refused == 1 and r.status == "complete" and r.answer_right


def test_a_sub_agents_room_does_not_depend_on_its_siblings(tmp_path: Path):
    """One finished crew trial stopped on 1 of 3 replays, 9 tokens over the cap: the room it kept was its
    sibling's reply, if that had arrived. The same replies must send a call or stop it, every time."""
    from taskorg.models import Slot

    engine = Engine(MemoryStore(tmp_path))
    m = new_run("room", "g", "p", "d")
    m.calls.extend([
        {"slot": "lead-1", "function": "lead", "completion_tokens": 100},
        {"slot": "w-a", "function": "worker", "completion_tokens": 300},
        {"slot": "w-b", "function": "worker", "completion_tokens": 3_000},
        {"slot": "w-c", "function": "worker", "completion_tokens": 9_000, "failed": True},
    ])
    worker = lambda name: Slot(id=f"w-{name}", function="worker", skill="retrieve", channel_id=name)
    assert engine._reply_room(m, worker("a")) == 300 and engine._reply_room(m, worker("b")) == 3_000
    assert engine._reply_room(m, worker("d")) == 0  # nothing of its own yet, and the lead's plan reply is no guide
    # After the split nothing is racing: the lead keeps room for the largest reply of all.
    assert engine._reply_room(m) == 3_000 and engine._reply_room(m, Slot(id="lead-1", function="lead", skill="reason")) == 3_000


def test_no_size_note_without_a_workspace(tmp_path: Path):
    assert "SIZE." not in _plan_packet(tmp_path, Replies(), Toolbox(), comparison_budget(40, 4000))


def test_replies_are_asked_to_be_brief():
    prompt = system_prompt(_brief())
    assert "evidence (array of strings): at most 5, each a short quote" in prompt
    assert "uncertainty (string): one sentence" in prompt and "Be brief" in prompt


def test_a_sub_agent_keeps_room_for_a_sub_agents_reply(tmp_path: Path):
    """One run stopped 44 tokens over the cap on a call that would have fit: a brief of about 6,036, plus 2,008 kept
    for the reply, and the 2,008 was the lead's plan reply. A small plan reply kept too little instead."""
    from taskorg.models import Slot

    class Measured(ModelAdapter):
        min_reply_tokens = 200
        part_reply_tokens = 1_500

    engine = Engine(MemoryStore(tmp_path), Measured())
    m = new_run("room", "g", "p", "d")
    worker = Slot(id="w-a", function="worker", skill="retrieve", channel_id="a")
    m.calls.append({"slot": "lead-1", "function": "lead", "completion_tokens": 2_008})
    assert engine._reply_room(m, worker) == 1_500
    assert engine._reply_room(m) == 2_008  # the lead's own calls still keep room for the lead's replies
    m.calls.append({"slot": "w-a", "function": "worker", "completion_tokens": 1_700})
    assert engine._reply_room(m, worker) == 1_700
    assert AnthropicAdapter.part_reply_tokens == 1_500 and LiveAdapter.part_reply_tokens == 0


def test_a_part_is_judged_by_a_sub_agents_call_and_the_whole_by_the_leads():
    from taskorg.gates import Subtask, assess

    parts = [Subtask("a", "x"), Subtask("b", "x")]
    sizes = {"a": {"a.md": 2_000}, "b": {"b.md": 1_000}}
    judge = lambda **kw: assess(parts, policy="measured", material=lambda s: sizes[s.channel_id], context_limit=4_000, **kw)
    # The lead's big plan reply leaves it 1,000, and a sub-agent's own call holds the part.
    assert all(v.legal for v in judge(overhead=3_000, part_overhead=2_000))
    assert judge(overhead=3_000)[0].refused == "a split does not make the work fit: one sub-task alone needs ~2000 tokens vs 1000 available per call"
    # A small plan reply leaves the lead plenty, and a sub-agent's call does not hold the part.
    v = judge(overhead=1_500, part_overhead=2_001)
    assert not any(a.legal for a in v) and "~2000 tokens vs 1999 available" in v[0].refused
    assert all(a.legal for a in judge(overhead=1_500, part_overhead=2_000))
    # Whether the whole fits one call is still the lead's sum: a sub-agent's figure does not change it.
    assert "fits in one context" in judge(overhead=1_000, part_overhead=9_000)[0].refused


def _groups_suite(tmp_path: Path):
    from taskorg.suite import build_suite, slug

    suite = build_suite(seed=7, per_family=1, families=("aggregate",), entities=10, distractors=6)
    task = suite.tasks[0]
    return task, [f"{slug(e)}.md" for e in task.entities], suite.write_corpus(tmp_path / "corpus")


def _planner(*plans):
    """A stand-in that plans as told, in order, writes each plan into the context as a real lead does, and
    otherwise works as the simulator does."""

    class Planner(SimModel):
        def __init__(self):
            super().__init__()
            self.plans, self.briefs, self.planned = list(plans), [], 0

        def act(self, brief):
            self.briefs.append(brief)
            art = super().act(brief)
            if brief.mode == "plan":
                self.planned += 1
                art.requests = self.plans.pop(0) if self.plans else []
                art.context_update = f"Plan number {self.planned}."
            return art

    return Planner()


def _group(name, files):
    return f"subtask:{name}@retrieve=figures_get_mixed {' '.join(files)}"


def _plans(adapter):
    return [b for b in adapter.briefs if b.mode == "plan"]


def test_a_plan_with_a_part_too_big_gets_a_second_try_told_why(tmp_path: Path):
    """A lead planned 8, 7 and 5 files at 20 companies. The gates were right to refuse, and working alone it
    overflowed on its next call, though the refusal said exactly what was wrong."""
    task, files, root = _groups_suite(tmp_path)
    adapter = _planner([_group("big", files[:8]), _group("rest", files[8:])],
                       [_group("left", files[:5]), _group("right", files[5:])])
    r = run_trial(task, "genet", adapter, root, budget=comparison_budget(40, 4_000), tool_rounds=4)
    first, second = _plans(adapter)
    assert "REFUSED" not in first.packet
    assert "YOUR FIRST PLAN WAS REFUSED: a split does not make the work fit: one sub-task alone needs" in second.packet
    assert "big (8 files, ~" in second.packet and "rest (2 files, ~" in second.packet
    assert "SIZE." in second.packet and "PLAN" in second.packet.upper()
    assert r.workers == 2 and r.refused == 0 and r.status == "complete" and r.answer_right
    # The first plan's parts never got a sub-agent, and the second's did.
    assert {b.channel_id for b in adapter.briefs if b.slot_function == "worker"} == {"left", "right"}
    # A plan writes itself into the shared context. The refused one is gone from all that follows.
    later = adapter.briefs[adapter.briefs.index(second):]
    assert not any("Plan number 1" in b.context for b in later)
    assert any("Plan number 2" in b.context for b in later if b.slot_function == "worker")


def test_the_second_plan_replaces_the_first_on_the_team_but_not_on_the_record(tmp_path: Path):
    from taskorg.diagnostics import diagnose
    from taskorg.review import part_statuses

    engine = Engine(MemoryStore(tmp_path))
    m = new_run("twice", "g", "p", "d")
    m._record("gate_overflow", {"proposed": 9, "considered": 6})
    m._record("gate", {"legal": False, "gate": "should_we", "channel_id": "big", "refused": "too big"})
    assert engine._cover(m, [], []) != "" and "big" in part_statuses(m)
    m._record("plan_refused", {"refused": "too big", "parts": "big (8 files, ~6,539 tokens)"})
    m._record("gate", {"legal": True, "gate": "", "channel_id": "left", "basis": "measured"})
    m._record("gate", {"legal": False, "gate": "could_we", "channel_id": "past", "refused": "no room"})
    # The first plan's overflow and its parts are no longer the lead's to cover or the team's to answer for.
    assert engine._cover(m, [], []) == ""
    assert "big" not in part_statuses(m) and part_statuses(m)["past"] == "no sub-agent; not covered"
    # They stay on the record.
    assert {"gate_overflow", "plan_refused"} <= {e.event for e in m.log}
    assert any(e.event == "gate" and e.detail["channel_id"] == "big" for e in m.log)
    assert any(i["event"] == "plan_refused" and i["detail"]["refused"] == "too big" for i in diagnose(m)["interactions"])


def test_there_is_no_third_plan(tmp_path: Path):
    task, files, root = _groups_suite(tmp_path)
    too_big = [_group("big", files[:8]), _group("rest", files[8:])]
    adapter = _planner(too_big, too_big, too_big)
    r = run_trial(task, "genet", adapter, root, budget=comparison_budget(40, 4_000), tool_rounds=4)
    assert len(_plans(adapter)) == 2 and r.workers == 0


def test_a_plan_refused_for_another_reason_gets_no_second_try(tmp_path: Path):
    task, files, root = _groups_suite(tmp_path)
    adapter = _planner([_group("left", files[:5]), _group("right", files[5:])], ["unused"])
    r = run_trial(task, "genet", adapter, root, budget=comparison_budget(40, 16_000), tool_rounds=4)
    assert len(_plans(adapter)) == 1 and r.workers == 0


@pytest.mark.parametrize("calls, plans", [(17, 1), (18, 2)])
def test_a_second_plan_needs_a_split_it_could_still_pay_for(tmp_path: Path, calls, plans):
    """The plan, two sub-agents of five calls each, a merge of five and the check: 17 after the first plan."""
    task, files, root = _groups_suite(tmp_path)
    too_big = [_group("big", files[:8]), _group("rest", files[8:])]
    adapter = _planner(too_big, too_big)
    run_trial(task, "genet", adapter, root, budget=comparison_budget(calls, 4_000), tool_rounds=4)
    assert len(_plans(adapter)) == plans


def test_a_tier_that_cannot_split_gets_no_second_plan(tmp_path: Path):
    task, files, root = _groups_suite(tmp_path)
    too_big = [_group("big", files[:8]), _group("rest", files[8:])]
    adapter = _planner(too_big, too_big)
    budget = comparison_budget(40, 4_000)
    budget.allow_split = False
    run_trial(task, "genet", adapter, root, budget=budget, tool_rounds=4)
    assert len(_plans(adapter)) == 1


def test_a_crew_is_never_refused_so_it_never_plans_twice(tmp_path: Path):
    task, files, root = _groups_suite(tmp_path)
    adapter = _planner([_group("big", files[:8]), _group("rest", files[8:])], ["unused"])
    run_trial(task, "always", adapter, root, budget=comparison_budget(40, 4_000), tool_rounds=4)
    assert len(_plans(adapter)) == 1


def test_the_gates_count_what_the_size_check_will(tmp_path: Path):
    """What the gates charge a part before its files is what its sub-agent's call then carries, so a part they
    pass is not stopped by the size check, on the adapter whose counts the size check uses."""
    from taskorg.adapters import TOOL_RESULTS
    from taskorg.gates import Subtask
    from taskorg.loop import READ_FRAME

    task, files, root = _groups_suite(tmp_path)
    adapter = AnthropicAdapter("", "claude-haiku-5-5", client=object())
    toolbox = Toolbox(roots=[root])
    engine = Engine(MemoryStore(tmp_path / "s"), adapter, budget=comparison_budget(40, 8_000), toolbox=toolbox, max_tool_rounds=4)
    m = new_run("frame", task.question, PURPOSE, DONE_WHEN)
    m.budget = engine.budget
    part = Subtask("left", "figures_get_mixed " + " ".join(files[:5]), skill="retrieve")
    other = Subtask("right", "figures_get_mixed " + " ".join(files[5:6]), skill="retrieve")
    slot = engine._worker_slot(part)
    brief = engine._worker_brief(m, slot, m.state.context, part.named_failure)
    frame = math.ceil(5 * READ_FRAME * TOKEN_RATIO)
    want = adapter.estimate_tokens(brief) + frame + AnthropicAdapter.part_reply_tokens
    assert engine._part_overhead(m, [part, other]) == want
    # The largest of the plan's parts sets it, and a proposal no sub-agent could take is not measured.
    bad = Subtask("bad", "x", skill="bogus")
    assert engine._part_overhead(m, [other, bad, part]) == want
    assert engine._part_overhead(m, [bad]) is None and engine._part_overhead(m, []) is None
    # The call after its reads comes to no more than the gates charged, and not far under.
    results = [toolbox.run(f"read:{f}", set()) for f in files[:5]]
    read = replace(brief, packet=f"{brief.packet}\n{TOOL_RESULTS}\n" + "\n\n".join(results))
    material = sum(engine._material(part).values())
    assert adapter.estimate_tokens(brief) + material < adapter.estimate_tokens(read) <= adapter.estimate_tokens(brief) + material + frame
    # With nothing to judge against, the gates fall back on the lead's figure.
    m.budget = None
    assert engine._part_overhead(m, [part]) is None
