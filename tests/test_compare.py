"""The comparison harness, checked offline with an oracle model that knows the answers."""

import json
from pathlib import Path

from taskorg.adapters import StubAdapter
from taskorg.cli import main
from taskorg.compare import comparison_budget, render, run_comparison, run_trial, summarize
from taskorg.models import Artifact
from taskorg.suite import FAMILIES, QUARTER_WORDS, build_suite, extract_answer, grade, slug


class Oracle(StubAdapter):
    """Answers correctly. Plans like each strategy's prompt asks: a crew always
    decomposes; a gated lead proposes one element per company only when there
    are several companies."""

    name = "oracle"

    def __init__(self, suite, *, verifier="PASS", answer_right=True):
        self.tasks = {t.question: t for t in suite.tasks}
        self.verifier = verifier
        self.answer_right = answer_right

    def act(self, brief):
        task = self.tasks[brief.effect]
        requests, claim = [], ""
        if brief.slot_function == "head" and brief.mode == "plan":
            if "You lead a crew" in brief.packet:
                requests = ["seam:find@retrieve=find_the_figure", "seam:check@retrieve=double_check_it"]
            elif len(task.entities) > 1:
                requests = [f"seam:{slug(e)}@retrieve=keep_companies_apart" for e in task.entities]
            claim = "plan"
        elif brief.slot_function == "verifier":
            claim = self.verifier
        elif brief.slot_function == "worker":
            claim = f"{brief.channel_id}: figure found"
        else:
            claim = f"Done. ANSWER: {task.answer if self.answer_right else 'nobody'}"
        return Artifact(claim=claim, evidence=[], uncertainty="oracle", channel_id="x", delta_to_picture=claim, requests=requests)


# --- suite ---


def test_suite_is_deterministic():
    a, b = build_suite(seed=3), build_suite(seed=3)
    assert a.corpus == b.corpus
    assert [(t.question, t.answer) for t in a.tasks] == [(t.question, t.answer) for t in b.tasks]
    assert build_suite(seed=4).corpus != a.corpus
    assert {t.family for t in a.tasks} == set(FAMILIES)


def test_ground_truth_is_stated_in_the_companys_own_file():
    suite = build_suite()
    for c in suite.companies.values():
        doc = suite.corpus[f"{slug(c.name)}.md"]
        for q in QUARTER_WORDS:
            assert f"{c.revenue[q]:.1f}" in doc and f"{c.churn[q]:.1f}" in doc
        assert f"{c.revenue_fy2025_q3:.1f}" in doc  # the distractor is there too
        if c.sister:
            assert c.sister in doc


def test_answers_follow_from_the_numbers():
    suite = build_suite()
    for t in suite.tasks:
        q = next(w for w in QUARTER_WORDS if f" {w} " in t.question)
        cos = [suite.companies[e] for e in t.entities]
        if t.family == "aggregate":
            assert abs(sum(c.revenue[q] for c in cos) - float(t.answer)) < 0.051
        elif t.family == "compare":
            assert t.answer == max(cos, key=lambda c: c.churn[q]).name
        elif t.family == "breadth":
            assert t.answer == max(cos, key=lambda c: c.revenue[q]).name


def test_grading():
    suite = build_suite()
    number = next(t for t in suite.tasks if t.kind == "number")
    name = next(t for t in suite.tasks if t.family == "compare")
    assert grade(f"${number.answer} million", number)
    assert not grade(str(float(number.answer) + 0.2), number)
    assert grade(name.answer.upper() + ".", name)
    look_alike = next(e for e in name.entities if e != name.answer)
    assert not grade(look_alike, name)
    assert not grade(None, name)
    assert extract_answer("thinking...\nANSWER: 1\nANSWER: 2") == "2"


# --- strategies ---


def test_strategies_organize_differently(tmp_path: Path):
    suite = build_suite(per_family=2)
    results = run_comparison(suite, lambda: Oracle(suite), corpus_dir=tmp_path / "corpus")
    by = {(r.strategy, r.task_id): r for r in results}
    for t in suite.tasks:
        assert by[("single", t.id)].workers == 0
        assert by[("always", t.id)].workers == 2
        # One element per company, up to the worker cap of 4; none for a single company.
        assert by[("genet", t.id)].workers == (min(len(t.entities), 4) if len(t.entities) > 1 else 0)
    assert all(r.correct for r in results)
    single_calls = {r.calls for r in results if r.strategy == "single"}
    assert single_calls == {2}  # work + verify, no planning call


def test_summary_and_report(tmp_path: Path):
    suite = build_suite(per_family=2)
    results = run_comparison(suite, lambda: Oracle(suite), corpus_dir=tmp_path / "c")
    summary = summarize(results, price_in=1.0, price_out=5.0)
    o = summary["overall"]
    assert o["genet"]["accuracy"] == o["single"]["accuracy"] == o["always"]["accuracy"] == 1.0
    assert o["single"]["split_rate"] == 0 and o["always"]["split_rate"] == 1
    assert 0 < o["genet"]["split_rate"] < 1
    lookup = summary["by_family"]["lookup"]
    assert lookup["genet"]["split_rate"] == 0 and lookup["always"]["split_rate"] == 1
    assert lookup["genet"]["tokens_mean"] < lookup["always"]["tokens_mean"]
    assert "cost_total" in o["genet"]
    text = render(summary)
    assert "## Overall" in text and "## Verdict" in text and "Genet tokens vs single" in text


def test_undelivered_answer_is_not_correct(tmp_path: Path):
    suite = build_suite(per_family=1, families=("lookup",))
    corpus = suite.write_corpus(tmp_path / "c")
    res = run_trial(suite.tasks[0], "single", Oracle(suite, verifier="FAIL"), corpus, budget=comparison_budget())
    assert res.status == "abort"
    assert res.answer_right and not res.correct
    wrong = run_trial(suite.tasks[0], "single", Oracle(suite, answer_right=False), corpus, budget=comparison_budget())
    assert wrong.status == "complete" and not wrong.correct


# --- CLI ---


def test_cli_compare_dry_run(capsys):
    assert main(["compare", "--dry-run", "--per-family", "2"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["trials"] == 2 * 4 * 3
    assert plan["call_ceiling"] == plan["trials"] * 40


def test_cli_compare_stub_saves(tmp_path: Path, capsys):
    out = tmp_path / "cmp.json"
    rc = main(["compare", "--per-family", "1", "--families", "lookup,aggregate", "--out", str(out)])
    assert rc == 0
    saved = json.loads(out.read_text())
    assert len(saved["results"]) == 2 * 3
    assert "## Overall" in capsys.readouterr().out


def test_cli_compare_rejects_unknown(capsys):
    assert main(["compare", "--strategies", "single,swarm", "--dry-run"]) == 1


def test_lead_covers_parts_past_the_worker_cap(tmp_path: Path):
    suite = build_suite(per_family=1, families=("breadth",))
    corpus = suite.write_corpus(tmp_path / "c")
    from taskorg.factory import element_at_rest
    from taskorg.compare import LOOK
    from taskorg.loop import Engine
    from taskorg.memory_store import MemoryStore
    from taskorg.tools import Toolbox

    m = element_at_rest("cap-1", suite.tasks[0].question, "p", "s")
    m.picture.success_criteria = ["ANSWER:"]
    Engine(MemoryStore(tmp_path / "s"), adapter=Oracle(suite), budget=comparison_budget(),
           toolbox=Toolbox(roots=[corpus])).run_mission(m, look_update=LOOK)
    assert m.picture.worker_count() == 4
    regroup = next(c for c in m.calls if c.get("mode") == "integrate")
    fifth = slug(suite.tasks[0].entities[4])
    assert f"yours to cover: {fifth}" in regroup["packet"]
    assert m.picture.slot("head-1").skill == "retrieve"
