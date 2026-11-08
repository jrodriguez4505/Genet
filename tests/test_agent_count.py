"""The agent-count sweep: compare's split-N strategies, where the kernel splits the files a question names into N
parts, and the worker cap an engine may set for it. The default cap stays 4, so every other run is as it was."""

import json
from pathlib import Path

import pytest

from taskorg import compare
from taskorg.compare import SWEEP, STRATEGIES, FixedSplit, comparison_budget, run_trial
from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.loop import MAX_PARTS, Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import MAX_WORKERS, Slot
from taskorg.sim import SimModel
from taskorg.suite import build_suite
from taskorg.tools import Toolbox


def _suite(entities=20):
    return build_suite(seed=113, per_family=1, families=("aggregate",), entities=entities, distractors=6)


def test_the_default_cap_is_four_and_a_sweep_may_set_another(tmp_path: Path):
    assert MAX_WORKERS == 4 and Engine(MemoryStore(tmp_path)).max_workers == 4
    assert Engine(MemoryStore(tmp_path), max_workers=20).max_workers == 20
    for bad in (0, MAX_PARTS + 1):
        with pytest.raises(ValueError):
            Engine(MemoryStore(tmp_path), max_workers=bad)


def test_a_run_holds_the_cap_its_engine_set(tmp_path: Path):
    run = new_run("r", goal="g", purpose="p", done_when="d")
    assert run.worker_cap == MAX_WORKERS
    Engine(MemoryStore(tmp_path), max_workers=6)._arm(run)
    assert run.worker_cap == 6
    lead = run.state.lead_id
    workers = [Slot(id=f"w{i}", function="worker", skill="retrieve", channel_id=f"c{i}") for i in range(7)]
    # Past the cap the roster is refused before anything else is checked.
    with pytest.raises(InvariantError, match="worker cap is 6"):
        run.set_roster(lead, run.state.slots + workers)


def test_the_split_strategies_are_registered_for_each_count():
    assert SWEEP == (2, 4, 10, 20)
    for n in SWEEP:
        engine = STRATEGIES[f"split-{n}"](MemoryStore(Path("/tmp/never-written")))
        assert isinstance(engine, FixedSplit) and engine.parts == n and engine.max_workers == n


@pytest.mark.parametrize("n", SWEEP)
def test_the_kernel_splits_the_named_files_evenly_in_order(tmp_path: Path, n: int):
    suite = _suite()
    root = suite.write_corpus(tmp_path / "corpus")
    task = suite.tasks[0]
    engine = STRATEGIES[f"split-{n}"](MemoryStore(tmp_path / "s"), toolbox=Toolbox(roots=[root]))
    run = new_run("r", goal=task.question, purpose="p", done_when="d")
    parts = engine._propose(run)
    assert [p.channel_id for p in parts] == [f"part-{k + 1:02d}" for k in range(n)]
    assert {p.skill for p in parts} == {"retrieve"}
    sizes = [len(engine.toolbox.material(p.channel_id, p.named_failure) or {}) for p in parts]
    # Every named company's file in exactly one part, the parts no more than one file apart.
    assert sum(sizes) == 20 and max(sizes) - min(sizes) <= 1
    covered = [f for p in parts for f in (engine.toolbox.material(p.channel_id, p.named_failure) or {})]
    assert len(covered) == len(set(covered)) == 20
    assert run.calls == []  # the kernel plans: no planning call


def test_a_sweep_trial_staffs_its_parts_and_answers_on_the_sim(tmp_path: Path):
    suite = _suite()
    root = suite.write_corpus(tmp_path / "corpus")
    for n in (4, 20):
        r = run_trial(suite.tasks[0], f"split-{n}", SimModel(), root, budget=comparison_budget(80, 8_000), tool_rounds=4)
        assert r.workers == n and r.correct, (n, r.code, r.answer)


def test_the_crew_still_stops_at_four_and_a_split_at_its_count(tmp_path: Path):
    from taskorg.gates import Subtask

    run = new_run("r", goal="g", purpose="p", done_when="d")
    parts = [Subtask(channel_id=f"c{i}", named_failure=f"read c{i}.md", skill="retrieve") for i in range(6)]
    for name, staffed in (("always", MAX_WORKERS), ("split-2", 2), ("split-10", 6)):
        verdicts = STRATEGIES[name](MemoryStore(tmp_path / name))._judge(run, parts)
        assert sum(v.legal for v in verdicts) == staffed, name
        assert all("worker cap" in v.refused for v in verdicts[staffed:]), name
