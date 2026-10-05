"""The deterministic reader: the corpus is readable, and every strategy can reach every answer."""

from pathlib import Path

from taskorg.cli import main
from taskorg.compare import run_comparison, summarize
from taskorg.sim import SimModel, facts, find_slugs, parse_question
from taskorg.suite import QUARTER_WORDS, build_suite, slug


def test_reader_recovers_every_fact_and_no_distractor():
    suite = build_suite()
    for c in suite.companies.values():
        got = facts(suite.corpus[f"{slug(c.name)}.md"])
        want = {("revenue", q): c.revenue[q] for q in QUARTER_WORDS} | {("churn", q): c.churn[q] for q in QUARTER_WORDS}
        assert got == want, c.name


def test_look_alike_names_stay_apart():
    assert find_slugs("read halvorsen-freight-labs.md then halvorsen-freight.md") == ["halvorsen-freight-labs", "halvorsen-freight"]
    # A brief names its channel several times; each company is read once.
    assert find_slugs("vantaro channel=vantaro only. note: read vantaro.md") == ["vantaro"]
    q = parse_question("Which had the higher FY2026 Q2 customer churn: Quillon Biologics or Quillon Bio?")
    assert q.slugs == ["quillon-biologics", "quillon-bio"] and q.kind == "max" and q.metric == "churn"


def test_every_strategy_can_reach_every_answer(tmp_path: Path):
    """If a perfect reader fails under a strategy, the harness is starving that strategy."""
    suite = build_suite()
    results = run_comparison(suite, SimModel, corpus_dir=tmp_path / "corpus")
    wrong = [(r.strategy, r.task_id, r.answer, r.expected) for r in results if not r.correct]
    assert not wrong, wrong


def test_structure_of_each_strategy(tmp_path: Path):
    suite = build_suite()
    s = summarize(run_comparison(suite, SimModel, corpus_dir=tmp_path / "corpus"))
    fam = s["by_family"]
    assert s["overall"]["single"]["split_rate"] == 0 and s["overall"]["single"]["calls_mean"] == 3
    assert fam["lookup"]["genet"]["split_rate"] == 0 and fam["lookup"]["always"]["split_rate"] == 1
    assert fam["lookup"]["genet"]["tokens_mean"] < fam["lookup"]["always"]["tokens_mean"]
    # With a perfect reader, splitting buys nothing: a single agent is cheapest everywhere.
    for block in fam.values():
        assert block["single"]["tokens_mean"] == min(v["tokens_mean"] for v in block.values())


def test_cli_compare_sim(tmp_path: Path, capsys):
    out = tmp_path / "sim.json"
    assert main(["compare", "--adapter", "sim", "--per-family", "1", "--out", str(out)]) == 0
    assert "| genet | 100% |" in capsys.readouterr().out


def test_genet_tracks_the_cheapest_strategy_that_works(tmp_path: Path):
    """Roomy context: genet stays a single agent. Tight context: a single agent overflows; genet fans out."""
    from taskorg.compare import comparison_budget

    suite = build_suite(per_family=2)
    strategies = ("single", "always", "genet")
    roomy = summarize(run_comparison(suite, SimModel, strategies=strategies, corpus_dir=tmp_path / "a"))["overall"]
    tight = summarize(run_comparison(suite, SimModel, strategies=strategies, corpus_dir=tmp_path / "b",
                                     budget_factory=lambda: comparison_budget(context=1500)))["overall"]
    assert roomy["genet"]["accuracy"] == 1.0 and roomy["genet"]["split_rate"] == 0
    assert roomy["genet"]["tokens_mean"] < 1.3 * roomy["single"]["tokens_mean"]
    assert roomy["genet"]["tokens_mean"] < roomy["always"]["tokens_mean"]
    assert tight["single"]["accuracy"] < 1.0 and tight["single"]["abort_rate"] > 0
    assert tight["genet"]["accuracy"] == 1.0 and tight["genet"]["split_rate"] > 0
    assert tight["genet"]["tokens_mean"] <= tight["always"]["tokens_mean"]


def test_tight_context_genet_splits_only_the_families_a_single_agent_fails(tmp_path: Path):
    """Per family: where a single agent gets every task right, genet does not split; where it gets none, genet splits every task."""
    from taskorg.compare import comparison_budget

    suite = build_suite()
    rows = summarize(run_comparison(suite, SimModel, strategies=("single", "genet"), corpus_dir=tmp_path / "c",
                                    budget_factory=lambda: comparison_budget(context=1500)))["by_family"]
    for family, row in rows.items():
        assert row["genet"]["accuracy"] == 1.0, family
        if row["single"]["accuracy"] == 1.0:
            assert row["genet"]["split_rate"] == 0, family
        if row["single"]["accuracy"] == 0:
            assert row["genet"]["split_rate"] == 1.0, family
    assert {f for f, r in rows.items() if r["single"]["accuracy"] == 1.0} == {"lookup", "compare"}
    assert rows["breadth"]["single"]["accuracy"] == 0
