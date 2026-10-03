from pathlib import Path

from taskorg.budget import Budget
from taskorg.factory import element_at_rest
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


def test_gold_never_proposes_on_crawl():
    m = element_at_rest("g1", "task", "purpose", "done")
    m.attach_budget(Budget.for_pace("crawl"))
    m.picture.context_sufficient = True
    assert gold_label(encode_board(m)) != "PROPOSE_CHANNEL"


def test_gold_holds_when_file_exists():
    m = element_at_rest("g2", "Write two notes", "Do not redo work", "Only open note")
    m.attach_budget(Budget.for_pace("run"))
    m.picture.context_sufficient = True
    m.world = World(existing_files=["note-a.txt"], existing_channels=["source-a"])
    assert gold_label(encode_board(m)) == "HOLD"


def test_imitation_matches_gold_invariants():
    pol = _head()
    crawl = element_at_rest("i1", "task", "purpose", "done")
    crawl.attach_budget(Budget.for_pace("crawl"))
    crawl.picture.context_sufficient = True
    assert pol.act(encode_board(crawl)).action != "PROPOSE_CHANNEL"

    exists = element_at_rest("i2", "Write two notes", "Do not redo work", "Only open")
    exists.attach_budget(Budget.for_pace("run"))
    exists.picture.context_sufficient = True
    exists.world = World(existing_files=["note-a.txt"], existing_channels=["source-a"])
    assert pol.act(encode_board(exists)).action == "HOLD"

    thin = element_at_rest("i3", "task", "purpose", "done")
    thin.picture.context_sufficient = False
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
