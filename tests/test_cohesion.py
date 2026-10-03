from pathlib import Path

import pytest

from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.gates import Seam
from taskorg.loop import Engine
from taskorg.memory_store import MemoryStore
from taskorg.models import Delta


def test_step_off_frozen_running_picture_moves():
    m = element_at_rest("coh-1", "Clear", "Deny", "Held")
    assert m.picture.step_off_picture == ""
    first = m.picture.current_picture
    m.update_context("head-1", "source-b is the seam")
    assert m.picture.step_off_picture == first
    assert m.picture.current_picture == "source-b is the seam"
    m.update_context("head-1", "contact on second deck")
    assert m.picture.step_off_picture == first
    assert m.picture.current_picture == "contact on second deck"


def test_element_delta_updates_living_picture():
    m = element_at_rest("coh-2", "Clear", "Deny", "Held")
    m.update_context("head-1", "initial context")
    m.post_delta(Delta(claim="source-a held", evidence=["w-source-a"], uncertainty="low", channel_id="source-a"))
    m.post_delta(Delta(claim="rear held", evidence=["w-rear"], uncertainty="low", channel_id="source-b"))
    assert "source-a held" in m.picture.current_picture
    assert "rear held" in m.picture.current_picture
    assert m.deltas[0].net == "element"


def test_unopened_out_net_illegal():
    m = element_at_rest("coh-3", "Clear", "Deny", "Held")
    with pytest.raises(InvariantError) as e:
        m.post_delta(
            Delta(claim="adjacent mark", evidence=[], uncertainty="n", channel_id="out", net="out")
        )
    assert e.value.code == "INV-13"
    m.write_net("head-1", "out")
    m.post_delta(Delta(claim="adjacent mark", evidence=[], uncertainty="n", channel_id="out", net="out"))


def test_worker_cannot_open_net():
    m = element_at_rest("coh-4", "Clear", "Deny", "Held")
    with pytest.raises(InvariantError) as e:
        m.write_net("w-source-a", "adjacent")
    assert e.value.code == "INV-13"


def test_sibling_channel_stripped_from_brief(tmp_path: Path):
    store = MemoryStore(tmp_path)
    store.remember_working("m", "look", "both seams")
    store.remember_working("m", "channel:source-a", "SECRET-ALLEY")
    store.remember_working("m", "channel:source-b", "SECRET-REAR")
    brief_a = store.scoped_brief("m", extra="act", channel_id="source-a")
    assert "SECRET-ALLEY" in brief_a
    assert "SECRET-REAR" not in brief_a
    rear = store.scoped_brief("m", extra="act", channel_id="source-b")
    assert "SECRET-REAR" in rear
    assert "SECRET-ALLEY" not in rear


def test_split_posts_element_deltas(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = element_at_rest("coh-5", "Clear", "Deny", "Held")
    Engine(store).run_multi_axis(
        m,
        look_update="two seams",
        seams=[Seam("source-a", "source-a channel"), Seam("source-b", "rear channel")],
        axes=["sequential", "fan_in"],
        operator_why="Is the living picture current?",
    )
    assert m.picture.step_off_picture
    assert any(d.net == "element" and d.channel_id == "source-a" for d in m.deltas)
    assert any(d.net == "element" and d.channel_id == "source-b" for d in m.deltas)
    assert m.picture.step_off_picture != m.picture.current_picture
