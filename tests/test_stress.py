"""Concurrency stress: sub-agents in threads must not lose, double-count or cross results."""

import random
import threading
import time
from pathlib import Path

from taskorg.adapters import StubAdapter
from taskorg.budget import Budget
from taskorg.diagnostics import diagnose
from taskorg.factory import new_run
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore

FOUR = " ".join(f"subtask:part-{c}=independent_{c}" for c in "abcd")


class Jitter(StubAdapter):
    """Stub with random delays, so sub-agents finish in a different order every run."""

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.lock = threading.Lock()

    def act(self, brief):
        with self.lock:
            delay = self.rng.uniform(0, 0.01)
        time.sleep(delay)
        return super().act(brief)


def _run(tmp_path: Path, i: int, budget: Budget | None = None):
    m = new_run(f"st-{i}", "Answer four parts", "Do not mix", "Integrated")
    Engine(MemoryStore(tmp_path / f"s{i}"), adapter=Jitter(i), budget=budget or Budget.for_tier("open")).run_task(m, context=FOUR)
    return m


def test_many_runs_with_four_parallel_sub_agents(tmp_path: Path):
    for i in range(25):
        m = _run(tmp_path, i)
        assert m.status.value == "complete"
        assert m.state.worker_count() == 4
        assert len(m.calls) == 7  # plan + 4 sub-agents + merge + verify
        assert sum(1 for e in m.log if e.event == "call") == 7
        assert [a.channel_id for a in m.artifacts if a.channel_id.startswith("part-")] == ["part-a", "part-b", "part-c", "part-d"]
        assert diagnose(m)["isolation"]["flags"] == []


def test_concurrent_runs_do_not_cross(tmp_path: Path):
    shared = Jitter(99)
    runs = [new_run(f"cc-{i}", f"Effect {i}", "Do not mix", "Integrated") for i in range(8)]
    errors = []

    def go(m):
        try:
            Engine(MemoryStore(tmp_path / m.id), adapter=shared, budget=Budget.for_tier("open")).run_task(m, context=FOUR)
        except Exception as e:  # noqa: BLE001 - the test reports any failure
            errors.append(e)

    threads = [threading.Thread(target=go, args=(m,)) for m in runs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    for i, m in enumerate(runs):
        assert m.status.value == "complete" and len(m.calls) == 7
        assert all(f"Effect {i}" in a.claim for a in m.artifacts if a.channel_id.startswith("part-"))


def test_tight_budget_never_overspends(tmp_path: Path):
    for calls in range(3, 9):
        m = new_run(f"tb-{calls}", "Answer four parts", "Do not mix", "Integrated")
        budget = Budget(max_calls=calls, max_tokens=100_000, max_tokens_per_call=10_000, tier="open")
        try:
            Engine(MemoryStore(tmp_path / f"t{calls}"), adapter=Jitter(calls), budget=budget).run_task(m, context=FOUR)
        except Exception:  # noqa: BLE001 - a halt is a legal outcome; overspend is not
            pass
        assert len(m.calls) <= calls
        if m.status.value == "complete":
            # The gates staffed only what the budget could pay for.
            workers = m.state.worker_count()
            assert len(m.calls) == (1 + workers + 2 if workers else 3)
