"""The independent verifier (docs/TEAM_DESIGN.md, part 2): what it sees, the sources the kernel opens for
it, and the verify bench that measures whether it catches a wrong product.

On 28 October a live verifier passed a wrong total. It had no sources and read the author's own notes.
These tests hold the fix: the kernel can show the verifier the sources and keep the notes from it, and
picks the files from the run's record, the same files every time.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from taskorg import checks
from taskorg.adapters import Brief, ModelAdapter
from taskorg.cli import main
from taskorg.errors import InvariantError
from taskorg.compare import SingleAgent, comparison_budget, run_comparison, task_context
from taskorg.factory import new_run
from taskorg.live import user_message
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact
from taskorg.sim import SimModel, contradicted, parse_question, stated
from taskorg.suite import build_suite, slug
from taskorg.tools import Toolbox
from taskorg import verify_bench as vb

NAMES = ["orbrook.md", "saffron-grid.md", "saffron-grid-partners.md", "tessaline.md", "ab.md"]


def _suite(questions=2, entities=20):
    return build_suite(seed=7, per_family=questions, families=("aggregate",), entities=entities, distractors=6)


class Capture(ModelAdapter):
    """The sim's replies, with every brief kept."""

    name = "capture"

    def __init__(self):
        self.briefs: list[Brief] = []
        self.sim = SimModel()

    def act(self, brief: Brief) -> Artifact:
        self.briefs.append(brief)
        return self.sim.act(brief)


def _review(tmp_path, setup, kind="look-alike", context=200_000, adapter=None):
    suite = _suite(1)
    root = suite.write_corpus(tmp_path / f"corpus-{setup}-{kind}")
    task, variant, built = next(item for item in vb.products(suite) if item[2].kind == kind)
    adapter = adapter or Capture()
    res = vb.review_trial(task, built, setup, adapter, root, budget=comparison_budget(4, context), variant=variant)
    return res, adapter, built


# --- what a tool result shows, and what the record keeps ---


def test_files_in_result_reads_and_searches():
    assert checks.files_in_result("[read notes/orbrook.md]\n# Orbrook") == {"read": ["notes/orbrook.md"]}
    assert checks.files_in_result("[read orbrook.md] already in full above") == {"read": ["orbrook.md"]}
    assert checks.files_in_result("[read nope.md] not found in the workspace") == {}
    out = "[retrieve q2 revenue]\na.md:3: Q2 revenue\nb-c.md:7: more\na.md:9: again\n[1 file(s) read in full above not searched again]"
    assert checks.files_in_result(out) == {"matched": ["a.md", "b-c.md"]}
    assert checks.files_in_result("[retrieve x] no matches") == {}
    assert checks.files_in_result("[observe] a.md") == {}


def test_a_run_records_the_files_its_tools_showed(tmp_path):
    suite = _suite(1, entities=3)
    root = suite.write_corpus(tmp_path / "corpus")
    task = suite.tasks[0]
    run = new_run("rec", goal=task.question, purpose="p", done_when="d")
    run.state.success_criteria = ["ANSWER:"]
    engine = SingleAgent(MemoryStore(tmp_path / "store"), adapter=SimModel(), budget=comparison_budget(20, 200_000),
                         toolbox=Toolbox(roots=[root]), max_tool_rounds=3)
    engine.run_task(run, context=task_context(task))
    read = checks.seen_files(run, ("read",))
    assert {f"{slug(n)}.md" for n in task.entities} <= read


# --- which files a check opens ---


def test_named_in_takes_the_longest_name_first():
    assert checks.named_in("Of Saffron Grid Partners and Orbrook, which?", NAMES) == ["saffron-grid-partners.md", "orbrook.md"]
    assert checks.named_in("Saffron Grid and Saffron Grid Partners", NAMES) == ["saffron-grid.md", "saffron-grid-partners.md"]
    assert checks.named_in("Saffron Grid's Q2", NAMES) == ["saffron-grid.md"]
    assert checks.named_in("the ab test", NAMES) == []  # a stem under three letters names nothing


def test_cited_in_keeps_look_alike_file_names_apart():
    text = 'saffron-grid-partners.md:5: "Revenue for Q2 reached $70.6 million." and Orbrook.md'
    assert checks.cited_in(text, NAMES) == ["saffron-grid-partners.md", "orbrook.md"]
    assert checks.cited_in("see saffron-grid.md", NAMES) == ["saffron-grid.md"]


def _run_with(goal, read=(), matched=()):
    run = new_run("p", goal=goal, purpose="p", done_when="d")
    for f in read:
        run._record("tool", {"read": [f]})
    if matched:
        run._record("tool", {"matched": list(matched)})
    return run


def _product(claim="Orbrook 40.0; Saffron Grid 70.6. ANSWER: 110.6", evidence=(), uncertainty="one sentence"):
    return Artifact(claim=claim, evidence=list(evidence), uncertainty=uncertainty, channel_id="lead-merge", context_update="")


def test_layered_opens_first_what_the_goal_names_and_the_run_never_saw():
    # The 28 October miss: the goal named Saffron Grid, and only its look-alike's file reached the run.
    run = _run_with("Combined revenue of Orbrook, Saffron Grid and Tessaline?", read=["orbrook.md", "tessaline.md"],
                    matched=["saffron-grid-partners.md"])
    picks = checks.pick(run, _product(), NAMES, "layered", sample=0)
    assert picks == [("saffron-grid.md", "the goal names it, and no call in the run read or searched it")]


def test_layered_adds_what_the_uncertainty_names_then_a_sample():
    run = _run_with("Combined revenue of Orbrook, Saffron Grid and Tessaline?", read=["orbrook.md", "saffron-grid.md", "tessaline.md"])
    p = _product(uncertainty="Saffron Grid was taken from saffron-grid-partners.md.")
    picks = checks.pick(run, p, NAMES, "layered", sample=2)
    assert picks[0] == ("saffron-grid-partners.md", "the product's uncertainty names it")
    assert [why for _, why in picks[1:]] == ["drawn at random"] * 2
    assert {n for n, _ in picks[1:]} <= {"orbrook.md", "saffron-grid.md", "tessaline.md"}
    # The same product opens the same files, whatever the run is called: a tape replays.
    assert checks.pick(replace(run, id="other"), p, NAMES, "layered", sample=2) == picks


def test_full_opens_everything_the_answer_rests_on_and_none_opens_nothing():
    run = _run_with("Revenue of Orbrook and Saffron Grid?", read=["tessaline.md"])
    p = _product(evidence=['saffron-grid-partners.md:5: "Revenue for Q2 reached $70.6 million."'])
    picks = dict(checks.pick(run, p, NAMES, "full"))
    assert picks == {
        "orbrook.md": "the goal names it", "saffron-grid.md": "the goal names it",
        "saffron-grid-partners.md": "the product cites it", "tessaline.md": "the run read it",
    }
    assert checks.pick(run, p, NAMES, "none") == []
    with pytest.raises(ValueError):
        checks.pick(run, p, NAMES, "some")


def test_misquoted_flags_a_quote_the_cited_file_does_not_hold(tmp_path):
    (tmp_path / "orbrook.md").write_text("# Orbrook\n\nThe company booked $40.0 million in revenue during Q2. Other text.\n")
    tb = Toolbox(roots=[tmp_path])
    names = tb.shown_files()
    good = _product(evidence=['orbrook.md:3: "The company booked $40.0 million in revenue during Q2."',
                              'orbrook.md: "The company booked ... in revenue during Q2"', "no quote here"])
    assert checks.misquoted(tb, good, names) == []
    bad = _product(evidence=['orbrook.md:3: "The company booked $44.0 million in revenue during Q2."'])
    assert checks.misquoted(tb, bad, names) == ['orbrook.md: orbrook.md:3: "The company booked $44.0 million in revenue during Q2."']


# --- what the verifier sees ---


def _verifier(adapter):
    return [b for b in adapter.briefs if b.slot_function == "verifier"][-1]


def test_the_default_verifier_brief_is_as_it_was(tmp_path):
    res, adapter, built = _review(tmp_path, "today")
    b = _verifier(adapter)
    assert b.view == "shared"
    assert "PRODUCT UNDER REVIEW (the lead's current product, the same as WORKING product)\n" in b.packet
    assert checks.SOURCES_HEAD not in b.packet and checks.SOURCE_RULE not in b.packet
    assert built.product.context_update in b.context  # today the verifier reads the author's note
    assert res.sources_shown == 0 and res.verdict == "PASS" and not res.right


def test_the_independent_view_leaves_out_the_authors_notes(tmp_path):
    res, adapter, built = _review(tmp_path, "independent-layered")
    b = _verifier(adapter)
    assert b.view == "independent"
    assert built.product.context_update not in b.context + b.packet
    working = b.packet.split("\nWORKING\n", 1)[1].split("\nBRIEF\n", 1)[0]
    assert '"product"' not in working and '"context"' in working
    assert b.packet.count(built.product.claim) == 1  # once, under PRODUCT UNDER REVIEW
    assert "PRODUCT UNDER REVIEW (the lead's current product)\n" in b.packet


def test_a_shared_view_with_sources_keeps_the_notes(tmp_path):
    _, adapter, built = _review(tmp_path, "shared-layered")
    b = _verifier(adapter)
    assert built.product.context_update in b.context and checks.SOURCES_HEAD in b.packet


def test_sources_are_trimmed_to_the_per_call_limit_and_say_so(tmp_path):
    res, adapter, _ = _review(tmp_path, "independent-full", context=6_000)
    b = _verifier(adapter)
    assert 0 < res.sources_shown < 20 and res.code in ("", "VERIFY")
    assert "more source(s) not shown: over the per-call limit]" in b.packet
    assert SimModel().estimate_tokens(b) <= 6_000


def test_the_sources_and_why_go_on_the_record(tmp_path):
    suite = _suite(1)
    root = suite.write_corpus(tmp_path / "c")
    task, _, built = next(i for i in vb.products(suite) if i[2].kind == "look-alike")
    run = new_run("rec", goal=task.question, purpose="p", done_when="d")
    run.state.success_criteria = ["ANSWER:"]
    for f in built.read:
        run._record("tool", {"read": [f]})
    engine = Engine(MemoryStore(tmp_path / "s"), adapter=SimModel(), budget=comparison_budget(4, 200_000),
                    toolbox=Toolbox(roots=[root]), verify_view="independent", verify_sources="layered")
    engine._arm(run)
    with pytest.raises(InvariantError):  # the verifier fails it, and a failed check halts the run
        engine._verify(run, built.product, adapt=False)
    rec = [e.detail for e in run.log if e.event == "verify_sources"][-1]
    assert rec["view"] == "independent" and rec["sources"] == "layered" and rec["shown"] == len(rec["picked"]) == 3
    assert rec["picked"][0] == {"file": built.error["own"], "why": "the goal names it, and no call in the run read or searched it"}
    assert [c.get("view") for c in run.calls] == ["independent"]


def test_the_engine_refuses_an_unknown_view_or_source_mode(tmp_path):
    with pytest.raises(ValueError):
        Engine(MemoryStore(tmp_path), verify_view="partial")
    with pytest.raises(ValueError):
        Engine(MemoryStore(tmp_path), verify_sources="some")


def test_the_verifier_request_is_the_same_every_time(tmp_path):
    a = _verifier(_review(tmp_path, "independent-layered")[1])
    b = _verifier(_review(tmp_path, "independent-layered")[1])
    assert user_message(a) == user_message(b)  # so a tape replays it


# --- the sim as a checker ---


def test_the_sim_reads_figures_both_ways_and_keeps_look_alikes_apart():
    q = parse_question("What was the combined FY2026 Q2 revenue, in $ millions, of Orbrook and Saffron Grid?")
    text = "Orbrook 40.0; Saffron Grid Partners 33.1; Saffron Grid 70.6\ntessaline revenue Q2 = 52.8"
    assert stated(text, q) == {"orbrook": 40.0, "saffron-grid-partners": 33.1, "saffron-grid": 70.6, "tessaline": 52.8}


def test_the_sim_fails_only_what_a_source_it_was_shown_contradicts():
    q = parse_question("What was the combined FY2026 Q2 revenue, in $ millions, of Orbrook and Saffron Grid?")
    packet = ("\nBRIEF\nPRODUCT UNDER REVIEW\nOrbrook 40.0; Saffron Grid 70.6. ANSWER: 110.6\n"
              f"{checks.SOURCES_HEAD}\n(picked: x)\n[read saffron-grid.md]\n# Saffron Grid\n\nRevenue for Q2 reached $61.1 million.\n")
    assert contradicted(q, packet) == "Saffron Grid 70.6 is not what saffron-grid.md says (61.1)"
    assert contradicted(q, packet.replace("$61.1", "$70.6")) == ""
    assert contradicted(q, packet.split(checks.SOURCES_HEAD)[0]) == ""


# --- the verify bench ---


def test_bench_products_plant_one_error_and_keep_the_arithmetic_right():
    suite = _suite(3)
    items = vb.products(suite)
    assert len(items) == 12 and sum(b.error is not None for _, _, b in items) == 6
    for task, _, built in items:
        figures = [float(x.rsplit(" ", 1)[1]) for x in built.product.claim.split(": ", 1)[1].split(". Total")[0].split("; ")]
        total = float(built.product.claim.rsplit("ANSWER: ", 1)[1])
        assert abs(sum(figures) - total) < 0.051
        assert len(figures) == len(task.entities) and len(built.product.evidence) == vb.EVIDENCE
        if built.kind == "look-alike":
            e = built.error
            assert e["used"] in built.read and e["own"] not in built.read and e["used"] != e["own"]
            assert e["stated"] == suite.companies[suite.companies[e["company"]].sister].revenue[vb._quarter(task)]
        elif built.kind == "wrong-year":
            e = built.error
            assert e["own"] in built.read and e["stated"] == suite.companies[e["company"]].revenue_fy2025_q3


def test_bench_on_the_sim_is_a_ceiling_for_each_setup():
    """A perfect checker of what it is shown: full catches every planted error, today none, and nothing
    right is failed. Layered catches every look-alike, since the author never opened the right file."""
    summary = vb.summarize(vb.run_bench(_suite(4), SimModel, budget_factory=lambda: comparison_budget(4, 200_000)))
    s = summary["setups"]
    assert s["today"]["caught"] == 0.0 and s["today"]["sources_mean"] == 0
    for setup in ("shared-full", "independent-full"):
        assert s[setup]["caught"] == 1.0 and s[setup]["error_shown"] == 1.0
    for setup in ("shared-layered", "independent-layered"):
        assert s[setup]["by_kind"]["look-alike"] == 1.0 and s[setup]["sources_mean"] < 4
    assert all(v["false_fail"] == 0.0 and v["errors"] == 0 for v in s.values())
    assert all(v["named"] == v["caught"] for v in s.values())  # the sim's FAIL names the figure it found


class Says(ModelAdapter):
    name = "says"

    def __init__(self, text: str):
        self.text = text

    def act(self, brief: Brief) -> Artifact:
        return Artifact(claim=self.text, evidence=[], uncertainty="u", channel_id="c", context_update="", requests=[])


def test_a_fail_names_the_error_only_outside_its_echo_of_the_product(tmp_path):
    """A verifier can fail a wrong product for another reason; repeating the product's list is not naming."""
    task, _, built = next(i for i in vb.products(_suite(1)) if i[2].kind == "look-alike")
    company = built.error["company"]
    other = next(n for n in task.entities if company not in n and n not in company)
    says = {
        f"FAIL: {company} {built.error['stated']:.1f} is a look-alike's figure.": True,
        f"FAIL. {built.product.claim} The figures are not all shown from the notes.": False,
        f"FAIL: {other} is not supported by an opened file.": False,
        "PASS": None,
    }
    for text, named in says.items():
        res, _, _ = _review(tmp_path, "today", adapter=Says(text))
        assert res.named is named, text


def test_the_bench_stops_at_a_spend_cap():
    calls = []

    def stop(done):
        calls.append(len(done))
        return "cap" if len(done) >= 3 else ""

    res = vb.run_bench(_suite(1), SimModel, budget_factory=lambda: comparison_budget(4, 200_000), stop_when=stop)
    assert len(res) == 3


def test_cli_verify_bench(tmp_path: Path, capsys):
    out = tmp_path / "v.json"
    assert main(["verify-bench", "--questions", "1", "--setups", "today,independent-full", "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["config"]["setups"] == ["today", "independent-full"] and data["config"]["reviews"] == 8
    assert set(data["summary"]["setups"]) == {"today", "independent-full"}
    assert "## Verify bench" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [
    ["--setups", "today,sometimes"],
    ["--max-spend", "1"],
    ["--price-in", "1"],
])
def test_cli_verify_bench_refuses(argv, capsys):
    assert main(["verify-bench", "--dry-run", *argv]) == 1
    assert '"VERIFY_BENCH"' in capsys.readouterr().out


def test_compare_carries_the_verifier_setting_and_the_sim_still_answers_everything(tmp_path):
    out = tmp_path / "c.json"
    assert main(["compare", "--adapter", "sim", "--families", "aggregate", "--per-family", "2", "--entities", "10",
                 "--distractors", "6", "--strategies", "single,genet", "--context", "200000",
                 "--verify-view", "independent", "--verify-sources", "full", "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["config"]["verify_view"] == "independent" and data["config"]["verify_sources"] == "full"
    assert all(r["correct"] for r in data["results"])


def test_compare_defaults_leave_the_verifier_as_it_was(tmp_path):
    suite = build_suite(seed=7, per_family=1)
    plain = run_comparison(suite, SimModel, strategies=("single", "genet"))
    same = run_comparison(suite, SimModel, strategies=("single", "genet"), verify={"verify_view": "shared", "verify_sources": "none"})
    assert [(r.correct, r.tokens, r.calls) for r in plain] == [(r.correct, r.tokens, r.calls) for r in same]


def test_run_commands_take_the_verifier_settings(tmp_path, capsys):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "orbrook.md").write_text("# Orbrook\n\nRevenue for Q2 reached $40.0 million.\n")
    out = tmp_path / "run.json"
    argv = ["run", "--tier", "normal", "--workspace", str(tmp_path / "notes"), "--goal", "Orbrook's Q2 revenue",
            "--context", "one note", "--out", str(out), "--verify-view", "independent", "--verify-sources", "full"]
    main(argv)
    log = json.loads(out.read_text())["log"]
    picked = [e["detail"] for e in log if e["event"] == "verify_sources"]
    assert picked and picked[0]["view"] == "independent" and picked[0]["picked"][0]["file"] == "orbrook.md"
    capsys.readouterr()
    out2 = tmp_path / "plain.json"
    main([a if a != str(out) else str(out2) for a in argv[:-4]])
    assert not any(e["event"] == "verify_sources" for e in json.loads(out2.read_text())["log"])
