"""When to split (--split-policy reads; compare's genet-reads). Under "measured" the gates admit a split when the goal's
files do not fit one call. With paged reads one agent reads a long file a page at a time and keeps what it found, so
under "reads" its need counts a page of each file: when that fits, there is no planning call and the lead works alone,
as one agent does. When it does not, the lead plans and the gates judge the plan as today. Unpaged work is measured
as it was, so every synthetic tape replays as it ran."""

from __future__ import annotations

import argparse

import pytest

from taskorg import compare
from taskorg.budget import Budget
from taskorg.cli import _add_run_args, _engine
from taskorg.gates import SPLIT_POLICIES, Subtask, assess
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.suite import Suite, Task

from bench_fake import BenchFake


def test_the_policy_is_named_and_measured_stays_the_default(tmp_path):
    assert SPLIT_POLICIES == ("measured", "stated", "reads")
    assert Engine(MemoryStore(tmp_path)).split_policy == "measured"
    with pytest.raises(ValueError, match="split_policy"):
        Engine(MemoryStore(tmp_path), split_policy="pages")


def test_the_gates_judge_a_plan_under_reads_as_under_measured():
    # The rule acts before a plan. A plan it lets happen is judged by the files' whole size, as today: one agent
    # could not hold a page of every file, so a split that covers only some of them still helps.
    subtasks = [Subtask(channel_id=f"p{i}", skill="retrieve", named_failure=f"report from p{i}.txt") for i in range(5)]
    sizes = {s.channel_id: {f"/w/{s.channel_id}.txt": n} for s, n in zip(subtasks, (30_000, 30_000, 1_000, 3_000, 120_000))}
    for picks in ([0, 1], [2, 3], [0, 4]):
        judged = {policy: [(v.legal, v.refused, v.basis) for v in assess(
            [subtasks[i] for i in picks], policy=policy, material=lambda s: sizes.get(s.channel_id),
            context_limit=100_000, fit_fraction=0.5)] for policy in ("measured", "reads")}
        assert judged["reads"] == judged["measured"]


# --- the engine: no planning call when one agent reading pages fits ---

def _question(tmp_path, n_files=3, chars=36_000):
    names = [f"f{i}" for i in range(n_files)]
    files = {f"q/{n}.txt": ("figure line\n" * (chars // 12)) for n in names}
    task = Task(id="q", family="f", question="Which is largest?", answer="rehearsal", kind="text", workspace="q",
                context="The files: " + ", ".join(f"{n}.txt" for n in names) + ".", purpose="End with ANSWER: <x>",
                done_when="ANSWER")
    return task, Suite(seed=0, companies={}, tasks=[task], corpus=files).write_corpus(tmp_path / "c")


class Spy(BenchFake):
    def __init__(self):
        super().__init__()
        self.briefs = []

    def act(self, brief):
        self.briefs.append(brief)
        return super().act(brief)


def _trial(task, root, strategy, context, page_chars=8000):
    spy, runs = Spy(), []
    orig = compare.new_run

    def grab(*a, **k):
        runs.append(orig(*a, **k))
        return runs[-1]

    compare.new_run = grab
    try:
        result = compare.run_trial(task, strategy, spy, root, budget=compare.comparison_budget(40, context),
                                   page_chars=page_chars)
    finally:
        compare.new_run = orig
    rule = [e.detail for e in runs[0].log if e.event == "split_rule"]
    return result, spy.briefs, rule


def _seen(briefs):
    return [(b.slot_function, b.mode, b.skill, b.packet) for b in briefs]


def test_where_one_agent_reading_pages_fits_genet_reads_works_alone_as_one_agent_does(tmp_path):
    # Three files of about 15,750 tokens each at a 40,000-token call: genet splits them (test_head_to_head), but a
    # page of each is about 10,600 against a room of 20,000.
    task, root = _question(tmp_path)
    genet, _, _ = _trial(task, root, "genet", 40_000)
    reads, briefs, rule = _trial(task, root, "genet-reads", 40_000)
    single, alone, _ = _trial(task, root, "single", 40_000)
    assert genet.workers == 3
    assert reads.workers == 0 and reads.proposed == 0 and reads.refused == 0
    assert not any(b.mode == "plan" for b in briefs)
    assert rule == [{"policy": "reads", "files": 3, "page_tokens": 3535, "need": 10_605, "room": 20_000, "plan": False}]
    # Request for request what one agent does, so a tape of one agent replays it.
    assert _seen(briefs) == _seen(alone) and (reads.answer, reads.tokens, reads.calls) == (single.answer, single.tokens, single.calls)


def test_where_a_page_of_each_file_does_not_fit_genet_reads_plans_and_splits_as_genet_does(tmp_path):
    task, root = _question(tmp_path, n_files=12)  # 12 pages of 3,535 against a room of 20,000
    genet, as_genet, _ = _trial(task, root, "genet", 40_000)
    reads, briefs, rule = _trial(task, root, "genet-reads", 40_000)
    assert [b.mode for b in briefs][:1] == ["plan"] and reads.workers == genet.workers == 4
    assert rule == [{"policy": "reads", "files": 12, "page_tokens": 3535, "need": 42_420, "room": 20_000, "plan": True}]
    assert sorted(_seen(briefs)) == sorted(_seen(as_genet))
    assert (reads.answer, reads.tokens, reads.calls) == (genet.answer, genet.tokens, genet.calls)


def test_unpaged_genet_reads_is_genet_request_for_request(tmp_path):
    task, root = _question(tmp_path, chars=6_000)
    genet, as_genet, _ = _trial(task, root, "genet", 4_000, page_chars=None)
    reads, briefs, rule = _trial(task, root, "genet-reads", 4_000, page_chars=None)
    # Sub-agents run side by side, so their briefs come in either order.
    assert rule == [] and genet.workers == 3 and sorted(_seen(briefs)) == sorted(_seen(as_genet))
    assert (reads.answer, reads.workers, reads.tokens, reads.calls) == (genet.answer, genet.workers, genet.tokens, genet.calls)


def test_the_rule_needs_a_call_limit_to_measure_against(tmp_path):
    task, root = _question(tmp_path)
    e = Engine(MemoryStore(tmp_path / "s"), adapter=BenchFake(), budget=Budget(max_tokens_per_call=0), split_policy="reads")
    assert e._one_agent_reads(compare.new_run("r", goal=task.question, purpose="p", done_when="d")) is False


def test_compare_and_run_take_the_rule(tmp_path):
    e = compare.STRATEGIES["genet-reads"](MemoryStore(tmp_path))
    assert type(e) is Engine and e.split_policy == "reads"
    assert compare.STRATEGIES["genet"](MemoryStore(tmp_path)).split_policy == "measured"
    p = argparse.ArgumentParser()
    _add_run_args(p, id="r", goal="g", purpose="p", done_when="d", context="c")
    assert _engine(p.parse_args(["--split-policy", "reads"]), MemoryStore(tmp_path / "s")).split_policy == "reads"
    assert _engine(p.parse_args([]), MemoryStore(tmp_path / "s")).split_policy == "measured"
