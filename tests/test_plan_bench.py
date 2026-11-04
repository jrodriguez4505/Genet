"""The plan bench: does a lead told why its first plan was refused write one that fits?

What the bench hands the run is fixed, and only the second planning call is the model's. So what it measures
can be checked here with stand-ins: a refusal it asks again after, plans that fit, plans that do not, plans that
leave files out, and a reply it cannot read. What a real lead writes is for a live run.
"""

import json
from pathlib import Path

import pytest

from taskorg import plan_bench as pb
from taskorg.adapters import ModelAdapter
from taskorg.anthropic_live import TOKEN_RATIO
from taskorg.cli import main
from taskorg.compare import comparison_budget
from taskorg.errors import InvariantError
from taskorg.models import Artifact
from taskorg.suite import build_suite, slug


def _suite(per_family=1):
    return build_suite(seed=7, per_family=per_family, families=("aggregate", "breadth"), entities=pb.ENTITIES, distractors=6)


class Lead(ModelAdapter):
    """Plans as told, one reply a call, and counts tokens as Claude does, so the first plan is refused."""

    name = "lead"
    token_ratio = TOKEN_RATIO
    part_reply_tokens = 1_500

    def __init__(self, plan=None, broken=False):
        self.plan, self.broken, self.briefs = plan, broken, []
        self.last_usage = {"prompt_tokens": 1_700, "completion_tokens": 900}

    def act(self, brief):
        self.briefs.append(brief)
        if self.broken:
            raise InvariantError("SCHEMA", "model JSON invalid")
        return Artifact(claim="plan", evidence=[], uncertainty="", channel_id="", context_update="",
                        requests=self.plan(brief))


def _groups(sizes, task):
    files = [f"{slug(e)}.md" for e in task.entities]
    out, start = [], 0
    for i, size in enumerate(sizes):
        out.append(f"subtask:part-{i}@retrieve=figures_get_mixed {' '.join(files[start:start + size])}")
        start += size
    return out


def _trial(tmp_path, adapter, shape="8-7-5", context=8_000):
    suite = _suite()
    task = suite.tasks[0]
    root = suite.write_corpus(tmp_path / "corpus")
    return task, pb.plan_trial(task, shape, adapter, root, budget=comparison_budget(40, context))


def test_every_shape_covers_the_files_a_question_names():
    task = _suite().tasks[0]
    for shape in pb.SHAPES.values():
        parts = pb.first_plan(task, shape)
        assert len(parts) == len(shape)
        named = [w for p in parts for w in p.named_failure.split() if w.endswith(".md")]
        assert sorted(named) == sorted(f"{slug(e)}.md" for e in task.entities)
        assert [sum(w.endswith(".md") for w in p.named_failure.split()) for p in parts] == list(shape)
    with pytest.raises(ValueError, match="does not cover"):
        pb.first_plan(task, (8, 7))


def test_a_refused_plan_is_told_why_and_a_plan_that_fits_is_admitted(tmp_path: Path):
    suite = _suite()
    task = suite.tasks[0]
    adapter = Lead(lambda brief: _groups((5, 5, 5, 5), task))
    root = suite.write_corpus(tmp_path / "corpus")
    r = pb.plan_trial(task, "8-7-5", adapter, root, budget=comparison_budget(40, 8_000))
    assert r.asked and r.parts == 4 and r.admitted == 4 and r.split
    assert r.files_per_part == [5, 5, 5, 5] and r.files_covered == r.files_wanted == 20 and r.refused == "" and r.code == ""
    # Only the second plan goes to the model, and it says what was wrong with the first.
    assert r.calls == 1 and len(adapter.briefs) == 1 and adapter.briefs[0].mode == "plan"
    assert "YOUR FIRST PLAN WAS REFUSED: a split does not make the work fit" in adapter.briefs[0].packet
    assert "group-a (8 files, ~" in adapter.briefs[0].packet and "group-c (5 files, ~" in adapter.briefs[0].packet
    assert r.tokens == 2_600 and r.prompt_tokens == 1_700 and r.largest > 0


def test_a_second_plan_too_big_is_refused_and_there_is_no_third(tmp_path: Path):
    suite = _suite()
    task = suite.tasks[0]
    adapter = Lead(lambda brief: _groups((10, 10), task))
    r = pb.plan_trial(task, "8-7-5", adapter, suite.write_corpus(tmp_path / "c"), budget=comparison_budget(40, 8_000))
    assert r.asked and r.parts == 2 and r.admitted == 0 and not r.split and r.calls == 1
    assert r.refused.startswith("a split does not make the work fit") and r.files_covered == 0 and r.largest == 0


def test_a_plan_that_fits_and_leaves_files_out_is_not_whole(tmp_path: Path):
    suite = _suite()
    task = suite.tasks[0]
    adapter = Lead(lambda brief: _groups((5, 5, 5), task))
    r = pb.plan_trial(task, "8-7-5", adapter, suite.write_corpus(tmp_path / "c"), budget=comparison_budget(40, 8_000))
    assert r.split and r.files_covered == 15 and r.files_wanted == 20
    s = pb.summarize([r])["shapes"]["8-7-5"]
    assert s["split"] == 1 and s["whole"] == 0 and s["still_refused"] == 0


def test_a_first_plan_that_fits_is_not_asked_again(tmp_path: Path):
    adapter = Lead(lambda brief: [])
    _, r = _trial(tmp_path, adapter, context=200_000)
    assert not r.asked and r.calls == 0 and adapter.briefs == []


def test_a_reply_it_cannot_read_is_counted_and_does_not_stop_the_bench(tmp_path: Path):
    suite = _suite()
    root = suite.write_corpus(tmp_path / "c")
    r = pb.plan_trial(suite.tasks[0], "8-7-5", Lead(broken=True), root, budget=comparison_budget(40, 8_000))
    assert r.code == "SCHEMA" and r.asked and not r.split
    s = pb.summarize([r])["shapes"]["8-7-5"]
    assert s["errors"] == 1 and s["still_refused"] == 0


def test_the_bench_runs_every_question_under_every_shape_and_stops_at_a_cap(tmp_path: Path):
    suite = _suite()
    tasks = {t.question: t for t in suite.tasks}
    factory = lambda: Lead(lambda brief: _groups((5, 5, 5, 5), tasks[brief.goal]))
    budget = lambda: comparison_budget(40, 8_000)
    lines = []
    done = pb.run_bench(suite, factory, budget_factory=budget, progress=lines.append)
    assert [(r.task_id, r.shape) for r in done] == [(t.id, s) for t in suite.tasks for s in pb.SHAPES]
    assert all(r.asked and r.split for r in done) and len(lines) == 6
    stopped = pb.run_bench(suite, factory, budget_factory=budget, progress=lines.append,
                           stop_when=lambda results: "cap" if len(results) >= 2 else "")
    assert len(stopped) == 2 and "stopped after 2 of 6 plans: cap" in lines[-1]
    again = pb.run_bench(suite, factory, repeats=2, shapes=("10-10",), budget_factory=budget)
    assert [r.repeat for r in again] == [0, 0, 1, 1]


def test_the_summary_says_what_a_plan_cost():
    r = pb.PlanResult(task_id="t", shape="10-10", repeat=0, asked=True, parts=4, admitted=4, split=True, files_wanted=20,
                      files_covered=20, largest=4_400, files_per_part=[5, 5, 5, 5], calls=1, tokens=2_600,
                      prompt_tokens=1_700, completion_tokens=900)
    s = pb.summarize([r], price_in=0.1, price_out=0.5)
    assert s["shapes"]["10-10"]["cost_total"] == round((1_700 * 0.1 + 900 * 0.5) / 1e6, 4)
    text = pb.render(s)
    assert "| 10-10 | 1 | 1 | 1 | 1 | 0 | 0 | 4,400 | 2,600 | $0.0006 |" in text
    assert "cost" not in pb.render(pb.summarize([r])).splitlines()[2]


def test_the_cli_plans_and_refuses_what_it_cannot_do(tmp_path: Path, capsys):
    out = tmp_path / "p.json"
    assert main(["plan-bench", "--adapter", "sim", "--shapes", "10-10", "--questions", "1", "--out", str(out)]) == 0
    saved = json.loads(out.read_text())
    assert saved["config"]["plans"] == 2 and saved["config"]["entities"] == 20 and len(saved["results"]) == 2
    capsys.readouterr()
    assert main(["plan-bench", "--adapter", "sim", "--dry-run", "--out", str(tmp_path / "d.json")]) == 0
    assert json.loads(capsys.readouterr().out)["plans"] == 18
    for bad in (["--shapes", "9-9"], ["--shapes", ""], ["--price-in", "0.1"], ["--max-spend", "0.1"], ["--record", "a", "--replay", "b"]):
        assert main(["plan-bench", "--adapter", "sim", *bad]) != 0
        assert json.loads(capsys.readouterr().out)["code"] == "PLAN_BENCH"
