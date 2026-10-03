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
    # With a perfect reader, splitting buys nothing: one body is cheapest everywhere.
    for block in fam.values():
        assert block["single"]["tokens_mean"] == min(v["tokens_mean"] for v in block.values())


def test_cli_compare_sim(tmp_path: Path, capsys):
    out = tmp_path / "sim.json"
    assert main(["compare", "--adapter", "sim", "--per-family", "1", "--out", str(out)]) == 0
    assert "| genet | 100% |" in capsys.readouterr().out
