"""The verify bench's two arms, and the abort criterion a run checks by default.

The arms put an argument in front of the verifier: the author's note arguing for the planted figure, or an
instruction in the source files the kernel opens. On the simulated reader, a perfect checker of what it is
shown, neither changes a verdict; what a model does with them is for a live run.
"""

import json
import re
from pathlib import Path

import pytest

from taskorg import verify_bench as vb
from taskorg.adapters import ModelAdapter
from taskorg.budget import Budget
from taskorg.cli import main
from taskorg.compare import comparison_budget
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Artifact
from taskorg.persist import load_run
from taskorg.sim import SimModel
from taskorg.situation import DEFAULT_ABORT
from taskorg.suite import build_suite, slug
from taskorg.tools import Toolbox


def _suite(questions=2):
    return build_suite(seed=7, per_family=questions, families=("aggregate",), entities=20, distractors=6)


def _by_arm(suite):
    out = {}
    for task, variant, built in vb.products(suite, vb.ARMS):
        out[(built.arm, task.id, built.kind, variant)] = (task, built)
    return out


# --- the arms ---


def test_the_note_arm_argues_for_the_planted_figure_and_changes_nothing_else():
    suite = _suite()
    items = _by_arm(suite)
    plain = {k[1:]: v for k, v in items.items() if k[0] == "plain"}
    noted = {k[1:]: v for k, v in items.items() if k[0] == "note"}
    assert noted and all(kind != "right" for _, kind, _ in noted)
    assert len(noted) == len([k for k in plain if k[1] != "right"])
    for key, (task, built) in noted.items():
        base = plain[key][1]
        assert built.product.claim == base.product.claim and built.product.evidence == base.product.evidence
        assert built.read == base.read and built.error == base.error and not built.plant
        note, e = built.product.context_update, built.error
        assert note != base.product.context_update
        assert e["company"] in note and f"{e['stated']:.1f}" in note and e["own"] in note
        if built.kind == "look-alike":
            assert e["used"] in note and suite.companies[e["company"]].sister in note
        else:
            assert f"{e['true']:.1f}" in note


def test_the_planted_arm_plants_an_instruction_in_every_goal_file_and_nowhere_else(tmp_path):
    suite = _suite(1)
    root = suite.write_corpus(tmp_path / "corpus")
    for key, (task, built) in _by_arm(suite).items():
        if built.arm != "planted":
            assert not built.plant and vb.corpus_for(built, root, tmp_path / "never") is root
            continue
        assert set(built.plant) == {f"{slug(n)}.md" for n in task.entities}
        text = vb.PLANTED_PASS if built.error is not None else vb.PLANTED_FAIL
        assert set(built.plant.values()) == {text}
        assert built.product == _by_arm(suite)[("plain",) + key[1:]][1].product
        copy = vb.corpus_for(built, root, tmp_path / "planted" / "-".join(map(str, key[1:])))
        assert copy != root and sorted(p.name for p in copy.glob("*.md")) == sorted(p.name for p in root.glob("*.md"))
        for path in root.glob("*.md"):
            before, after = path.read_text(), (copy / path.name).read_text()
            if path.name in built.plant:
                assert after.endswith(text + "\n") and after.startswith(before.rstrip("\n"))
            else:
                assert after == before
    assert not (tmp_path / "never").exists()


def test_a_planted_review_opens_the_planted_file_and_the_plain_corpus_stays_clean(tmp_path):
    suite = _suite(1)
    root = suite.write_corpus(tmp_path / "corpus")
    task, variant, built = next(i for i in vb.products(suite, ("planted",)) if i[2].kind == "look-alike")
    where = vb.corpus_for(built, root, tmp_path / "planted")
    res = vb.review_trial(task, built, "shared-full", SimModel(), where, budget=comparison_budget(4, 200_000), variant=variant)
    assert res.arm == "planted" and res.verdict == "FAIL" and res.error_shown
    assert vb.PLANTED_PASS in (where / built.error["own"]).read_text()
    assert vb.PLANTED_PASS not in (root / built.error["own"]).read_text()


def test_arms_on_the_sim_are_a_ceiling():
    """A perfect checker of what it is shown reads a note as a note and an instruction as text."""
    summary = vb.summarize(vb.run_bench(_suite(3), SimModel, setups=("shared-layered", "independent-full"),
                                        arms=("plain", "note", "planted"), budget_factory=lambda: comparison_budget(4, 200_000)))
    s = summary["setups"]
    assert set(s) == {"shared-layered", "shared-layered / note", "shared-layered / planted",
                      "independent-full", "independent-full / note", "independent-full / planted"}
    for setup in ("shared-layered", "independent-full"):
        for arm in ("note", "planted"):
            assert s[f"{setup} / {arm}"]["caught"] == s[setup]["caught"]
            assert s[f"{setup} / {arm}"]["by_kind"] == s[setup]["by_kind"]
        assert s[f"{setup} / note"]["false_fail"] is None and s[f"{setup} / note"]["n"] == 6
        assert s[f"{setup} / planted"]["false_fail"] == 0.0 and s[f"{setup} / planted"]["n"] == 12
    assert all(v["errors"] == 0 for v in s.values())
    text = vb.render(summary)
    assert "| shared-layered / note |" in text and "note: the author's note" in text and "planted: every file" in text


def test_products_default_to_the_plain_arm_and_refuse_an_unknown_one():
    suite = _suite(1)
    assert [b.arm for _, _, b in vb.products(suite)] == ["plain"] * 4
    assert len(vb.products(suite, vb.ARMS)) == 4 + 2 + 4 + 6
    with pytest.raises(ValueError, match="arm"):
        vb.build(suite, suite.tasks[0], "right", arm="loud")


def test_cli_verify_bench_arms(tmp_path: Path, capsys):
    out = tmp_path / "v.json"
    assert main(["verify-bench", "--questions", "1", "--setups", "today", "--arms", "plain,note,planted", "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["config"]["arms"] == ["plain", "note", "planted"] and data["config"]["reviews"] == 10
    assert set(data["summary"]["setups"]) == {"today", "today / note", "today / planted"}
    assert {r["arm"] for r in data["results"]} == {"plain", "note", "planted"}
    assert main(["verify-bench", "--dry-run", "--arms", "plain,loud"]) == 1
    assert '"VERIFY_BENCH"' in capsys.readouterr().out


# --- the default view ---


def test_the_independent_view_is_the_default_and_a_note_does_not_reach_it(tmp_path):
    """With every source open, a false note got 5 of 6 look-alike errors past the shared view, and none past this."""
    assert Engine(MemoryStore(tmp_path / "a")).verify_view == "independent"
    out = tmp_path / "plain.json"
    assert main(["compare", "--adapter", "sim", "--per-family", "1", "--families", "lookup", "--strategies", "single",
                 "--out", str(out)]) == 0
    assert json.loads(out.read_text())["config"]["verify_view"] == "independent"
    assert main(["single", "--tier", "tight", "--store", str(tmp_path / "s"), "--context", "c",
                 "--out", str(tmp_path / "r.json"), "--verify-view", "shared"]) == 0


# --- the default abort criterion ---


def test_a_new_run_checks_forecast_short_by_default():
    assert DEFAULT_ABORT == ("forecast_short",)
    assert new_run("r", goal="g", purpose="p", done_when="d").state.abort_criteria == ["forecast_short"]


@pytest.mark.parametrize("argv, expected", [
    ([], ["forecast_short"]),
    (["--abort", "none"], []),
    (["--abort", "parts_failed:2"], ["parts_failed:2"]),
    (["--abort", "none", "--abort", "parts_failed:1"], ["parts_failed:1"]),
])
def test_cli_abort_flag_replaces_the_default_and_none_turns_it_off(tmp_path: Path, argv, expected):
    out = tmp_path / "run.json"
    assert main(["single", "--tier", "tight", "--store", str(tmp_path / "store"), "--out", str(out), *argv]) == 0
    assert load_run(out).state.abort_criteria == expected


def test_a_run_that_cannot_finish_stops_at_its_plan_by_default(tmp_path):
    """The suite's own case: 4,000 tokens a call against a budget of 10,000. Without the criterion the run
    makes three calls and stops on its budget; with it, one."""
    class Wide(ModelAdapter):
        """Every call costs 4,000 tokens, and the lead proposes nothing."""

        name = "wide"

        def act(self, brief):
            self.last_usage = {"prompt_tokens": 3_500, "completion_tokens": 500}
            claim = "PASS criterion" if brief.slot_function == "verifier" else "criterion ANSWER: 1"
            return Artifact(claim=claim, evidence=[], uncertainty="", channel_id=brief.channel_id or "lead",
                            context_update="", requests=[])

    def attempt(criteria):
        run = new_run("r", goal="Write the note", purpose="p", done_when="d")
        run.state.success_criteria = ["criterion"]
        run.state.abort_criteria = criteria
        budget = Budget(max_calls=8, max_tokens=10_000, max_seconds=60, max_tokens_per_call=8_000,
                        allow_split=True, allow_adapt=True, tier="bench")
        try:
            Engine(MemoryStore(tmp_path / "s"), adapter=Wide(), budget=budget, toolbox=Toolbox(roots=[])).run_task(run, context="c")
        except InvariantError as e:
            return run, e.code
        return run, ""

    default, code = attempt(new_run("x", goal="g", purpose="p", done_when="d").state.abort_criteria)
    off, code_off = attempt([])
    assert code == "ABORT" and len(default.calls) == 1 and "forecast_short" in default.review["what_failed"][0]
    assert code_off == "BUDGET" and len(off.calls) > len(default.calls)


# --- the split arm, and the verifier told its sources are a sample


def _split(questions=2):
    return [x for x in vb.products(_suite(questions), ("split",))]


def test_a_split_product_reads_as_a_merge_and_adds_up():
    for task, variant, built in _split():
        p = built.product
        assert built.arm == "split" and p.uncertainty == vb.SPLIT_UNCERTAINTY
        groups = re.findall(r"group-[a-d] ([\d.]+) \(([^)]*)\)", p.claim)
        assert len(groups) == vb.SPLIT_GROUPS and len(p.evidence) == vb.SPLIT_GROUPS
        figures = [float(f.rsplit(" ", 1)[1]) for _, names in groups for f in names.split(", ")]
        assert len(figures) == len(task.entities)
        for subtotal, names in groups:
            assert abs(float(subtotal) - sum(float(f.rsplit(" ", 1)[1]) for f in names.split(", "))) < 0.05
        total = re.search(r"ANSWER: ([\d.]+)$", p.claim).group(1)
        assert abs(float(total) - sum(figures)) < 0.05
        # As after a real split: the lead cites its sub-agents, not a file, and the run read them all.
        assert ".md" not in p.claim and not any(".md" in e for e in p.evidence)
        assert sorted(built.read) == sorted(f"{slug(n)}.md" for n in task.entities)


def test_each_question_has_every_split_product_with_its_error_where_the_variant_asks():
    suite = _suite()
    items = vb.products(suite, ("split",))
    assert len(items) == 2 * len(vb.SPLIT_VARIANTS)
    assert len({b.product.claim for _, _, b in items}) == len(items)
    for task, variant, built in items:
        if built.kind == "right":
            assert built.error is None and str(task.answer) in built.product.claim
            continue
        own = built.error["own"]
        assert (own in vb._drawn(suite, task, built.product, built.read)) == (variant == 0)
        assert str(built.error["stated"]) in built.product.claim
        assert built.error["stated"] != built.error["true"]


def test_a_split_product_it_cannot_place_is_left_out():
    suite = _suite(1)
    task = suite.tasks[0]
    original = vb.SPLIT_TRIES
    vb.SPLIT_TRIES = 0
    try:
        assert vb.build(suite, task, "wrong-year", 0, "split") is None
    finally:
        vb.SPLIT_TRIES = original
    assert vb.build(suite, task, "right", 0, "split") is not None


def test_a_perfect_checker_catches_only_what_it_was_shown(tmp_path: Path):
    """The simulated reader fails what a file it was shown contradicts, and cannot fail what it was not shown. So
    this is what a check that never refuses looks like, and the line a real verifier is measured against."""
    results = vb.run_bench(_suite(), SimModel, setups=("independent-layered", "independent-told"), arms=("split",),
                           budget_factory=lambda: comparison_budget(4, 8_000))
    assert len(results) == 2 * 2 * len(vb.SPLIT_VARIANTS)
    for r in results:
        if r.kind != "right":
            assert r.error_shown == (r.variant == 0) and r.sources_shown == 2
    summary = vb.summarize(results)["setups"]
    for label in ("independent-layered / split", "independent-told / split"):
        assert summary[label]["false_fail"] == 0 and summary[label]["caught_shown"] == 1 and summary[label]["caught_unseen"] == 0
    text = vb.render(vb.summarize(results))
    assert "| independent-told / split | 0% | 100% | 0% |" in text and "wrong caught, its file not shown" in text
    assert "not shown" not in vb.render(vb.summarize([r for r in results if r.arm != "split"]))


class _Reads(ModelAdapter):
    def __init__(self):
        self.packets = []

    def act(self, brief):
        self.packets.append(brief.packet)
        return Artifact(claim="PASS. Fine.", evidence=[], uncertainty="", channel_id="", context_update="", requests=[])


def test_only_the_told_setup_tells_the_verifier_its_sources_are_a_sample(tmp_path: Path):
    from taskorg.checks import HEADING_RULE, SAMPLE_RULE, SOURCE_RULE

    suite = _suite(1)
    root = suite.write_corpus(tmp_path / "corpus")
    task, _, built = vb.products(suite, ("split",))[0]
    said = {}
    for setup in vb.SETUPS:
        reads = _Reads()
        vb.review_trial(task, built, setup, reads, root, budget=comparison_budget(4, 8_000))
        said[setup] = reads.packets[-1]
    assert SAMPLE_RULE in said["independent-told"] and said["independent-told"].count(SOURCE_RULE) == 1
    assert HEADING_RULE in said["independent-headed"] and SAMPLE_RULE not in said["independent-headed"]
    assert SOURCE_RULE + SAMPLE_RULE + HEADING_RULE in said["independent-both"]
    for setup in vb.DEFAULT_SETUPS:
        assert SAMPLE_RULE not in said[setup] and HEADING_RULE not in said[setup]
    # The same brief as independent-layered, but for the sentences.
    for setup, note in vb.TOLD.items():
        assert said[setup].replace(note, "") == said["independent-layered"]


def test_a_plain_run_of_the_bench_leaves_out_the_told_setup(tmp_path: Path):
    assert vb.DEFAULT_SETUPS == ("today", "shared-full", "shared-layered", "independent-full", "independent-layered")
    assert set(vb.SETUPS) - set(vb.DEFAULT_SETUPS) == set(vb.TOLD)
    out = tmp_path / "v.json"
    assert main(["verify-bench", "--adapter", "sim", "--questions", "1", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["config"]["setups"] == list(vb.DEFAULT_SETUPS)
    results = vb.run_bench(_suite(1), SimModel, budget_factory=lambda: comparison_budget(4, 200_000))
    assert {r.setup for r in results} == set(vb.DEFAULT_SETUPS)
    assert Engine(MemoryStore(tmp_path / "s")).verify_note == ""
