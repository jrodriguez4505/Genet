from pathlib import Path

import pytest

from taskorg.errors import InvariantError
from taskorg.factory import new_run
from taskorg.gates import Subtask
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Delta


def test_initial_context_frozen_live_context_moves():
    m = new_run("coh-1", "Summarize the notes", "Keep sources apart", "Summary written")
    assert m.state.initial_context == ""
    first = m.state.context
    m.update_context("lead-1", "source-b is the subtask")
    assert m.state.initial_context == first
    assert m.state.context == "source-b is the subtask"
    m.update_context("lead-1", "new data in section two")
    assert m.state.initial_context == first
    assert m.state.context == "new data in section two"


def test_merge_delta_updates_live_context():
    m = new_run("coh-2", "Summarize the notes", "Keep sources apart", "Summary written")
    m.update_context("lead-1", "initial context")
    m.post_delta(Delta(claim="source-a held", evidence=["w-source-a"], uncertainty="low", channel_id="source-a"))
    m.post_delta(Delta(claim="note B done", evidence=["w-source-b"], uncertainty="low", channel_id="source-b"))
    assert "source-a held" in m.state.context
    assert "note B done" in m.state.context
    assert m.deltas[0].stream == "merge"


def test_unopened_out_net_illegal():
    m = new_run("coh-3", "Summarize the notes", "Keep sources apart", "Summary written")
    with pytest.raises(InvariantError) as e:
        m.post_delta(
            Delta(claim="adjacent mark", evidence=[], uncertainty="n", channel_id="report", stream="report")
        )
    assert e.value.code == "INV-13"
    m.open_stream("lead-1", "report")
    m.post_delta(Delta(claim="adjacent mark", evidence=[], uncertainty="n", channel_id="report", stream="report"))


def test_worker_cannot_open_net():
    m = new_run("coh-4", "Summarize the notes", "Keep sources apart", "Summary written")
    with pytest.raises(InvariantError) as e:
        m.open_stream("w-source-a", "peer")
    assert e.value.code == "INV-13"


def test_sibling_channel_stripped_from_brief(tmp_path: Path):
    store = MemoryStore(tmp_path)
    store.remember_working("m", "context", "both subtasks")
    store.remember_working("m", "channel:source-a", "SECRET-A")
    store.remember_working("m", "channel:source-b", "SECRET-B")
    brief_a = store.scoped_brief("m", extra="act", channel_id="source-a")
    assert "SECRET-A" in brief_a
    assert "SECRET-B" not in brief_a
    brief_b = store.scoped_brief("m", extra="act", channel_id="source-b")
    assert "SECRET-B" in brief_b
    assert "SECRET-A" not in brief_b


def test_split_posts_merge_deltas(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = new_run("coh-5", "Summarize the notes", "Keep sources apart", "Summary written")
    Engine(store).run_fanout(
        m,
        context="two subtasks",
        subtasks=[Subtask("source-a", "source-a channel"), Subtask("source-b", "source-b channel")],
        axes=["sequential", "fan_in"],
        operator_question="Is the live context current?",
    )
    assert m.state.initial_context
    assert any(d.stream == "merge" and d.channel_id == "source-a" for d in m.deltas)
    assert any(d.stream == "merge" and d.channel_id == "source-b" for d in m.deltas)
    assert m.state.initial_context != m.state.context
