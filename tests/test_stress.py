"""Concurrency stress: elements in threads must not lose, double-count or cross results."""

import random
import threading
import time
from pathlib import Path

from taskorg.adapters import StubAdapter
from taskorg.budget import Budget
from taskorg.diagnostics import diagnose
from taskorg.factory import element_at_rest
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore

FOUR = " ".join(f"seam:part-{c}=independent_{c}" for c in "abcd")


class Jitter(StubAdapter):
    """Stub with random delays, so elements finish in a different order every run."""

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.lock = threading.Lock()

    def act(self, brief):
        with self.lock:
            delay = self.rng.uniform(0, 0.01)
        time.sleep(delay)
        return super().act(brief)


def _run(tmp_path: Path, i: int, budget: Budget | None = None):
    m = element_at_rest(f"st-{i}", "Answer four parts", "Do not mix", "Integrated")
    Engine(MemoryStore(tmp_path / f"s{i}"), adapter=Jitter(i), budget=budget or Budget.for_pace("run")).run_mission(m, look_update=FOUR)
    return m


def test_many_missions_with_four_parallel_elements(tmp_path: Path):
    for i in range(25):
        m = _run(tmp_path, i)
        assert m.status.value == "complete"
        assert m.picture.worker_count() == 4
        assert len(m.calls) == 7  # plan + 4 elements + regroup + verify
        assert sum(1 for e in m.log if e.event == "call") == 7
        assert [a.channel_id for a in m.artifacts if a.channel_id.startswith("part-")] == ["part-a", "part-b", "part-c", "part-d"]
        assert diagnose(m)["isolation"]["flags"] == []


def test_concurrent_missions_do_not_cross(tmp_path: Path):
    shared = Jitter(99)
    missions = [element_at_rest(f"cc-{i}", f"Effect {i}", "Do not mix", "Integrated") for i in range(8)]
    errors = []

    def go(m):
        try:
            Engine(MemoryStore(tmp_path / m.id), adapter=shared, budget=Budget.for_pace("run")).run_mission(m, look_update=FOUR)
        except Exception as e:  # noqa: BLE001 - the test reports any failure
            errors.append(e)

    threads = [threading.Thread(target=go, args=(m,)) for m in missions]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    for i, m in enumerate(missions):
        assert m.status.value == "complete" and len(m.calls) == 7
        assert all(f"Effect {i}" in a.claim for a in m.artifacts if a.channel_id.startswith("part-"))


def test_tight_budget_never_overspends(tmp_path: Path):
    for calls in range(3, 9):
        m = element_at_rest(f"tb-{calls}", "Answer four parts", "Do not mix", "Integrated")
        budget = Budget(max_calls=calls, max_tokens=100_000, max_tokens_per_call=10_000, pace="run")
        try:
            Engine(MemoryStore(tmp_path / f"t{calls}"), adapter=Jitter(calls), budget=budget).run_mission(m, look_update=FOUR)
        except Exception:  # noqa: BLE001 - a halt is a legal outcome; overspend is not
            pass
        assert len(m.calls) <= calls
        if m.status.value == "complete":
            # The gates staffed only what the budget could pay for.
            workers = m.picture.worker_count()
            assert len(m.calls) == (1 + workers + 2 if workers else 3)
