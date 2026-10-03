from pathlib import Path

from taskorg.budget import Budget
from taskorg.factory import new_run
from taskorg.gates import World
from taskorg.imitate import (
    ImitationPolicy,
    confusion,
    dump,
    fit,
    gold_label,
    load,
    synthesize,
    vs_stub,
)
from taskorg.policy import encode_board


def _head():
    return ImitationPolicy.train_default()


def test_gold_never_proposes_on_tight():
    m = new_run("g1", "task", "purpose", "done")
    m.attach_budget(Budget.for_tier("tight"))
    m.state.context_sufficient = True
    assert gold_label(encode_board(m)) != "PROPOSE_CHANNEL"


def test_gold_holds_when_file_exists():
    m = new_run("g2", "Write two notes", "Do not redo work", "Only open note")
    m.attach_budget(Budget.for_tier("open"))
    m.state.context_sufficient = True
    m.world = World(existing_files=["note-a.txt"], existing_channels=["source-a"])
    assert gold_label(encode_board(m)) == "HOLD"


def test_imitation_matches_gold_invariants():
    pol = _head()
    tight = new_run("i1", "task", "purpose", "done")
    tight.attach_budget(Budget.for_tier("tight"))
    tight.state.context_sufficient = True
    assert pol.act(encode_board(tight)).action != "PROPOSE_CHANNEL"

    exists = new_run("i2", "Write two notes", "Do not redo work", "Only open")
    exists.attach_budget(Budget.for_tier("open"))
    exists.state.context_sufficient = True
    exists.world = World(existing_files=["note-a.txt"], existing_channels=["source-a"])
    assert pol.act(encode_board(exists)).action == "HOLD"

    thin = new_run("i3", "task", "purpose", "done")
    thin.state.context_sufficient = False
    assert pol.act(encode_board(thin)).action == "INSPECT"


def test_fit_accuracy_and_dump(tmp_path: Path):
    rows = synthesize(120)
    train, held = rows[:80], rows[80:]
    head = fit(train, steps=200)
    pol = ImitationPolicy(head)
    report = confusion(held or train, pol)
    assert report["accuracy"] >= 0.9
    path = dump(head, tmp_path / "imitation.json")
    again = ImitationPolicy(load(path))
    assert again.act(held[0][0] if held else train[0][0]).action in {
        "HOLD", "INSPECT", "CHANGE_METHOD", "PROPOSE_CHANNEL", "STOP",
    }
    stub = vs_stub(rows)
    assert stub["stub_vs_gold"] >= 0.8
