from taskorg.imitate import ImitationPolicy
from taskorg.policy import StubPolicy
from taskorg.rl import compare_to_stub, evaluate, step, train


def test_stub_does_not_spawn_on_tight_or_exists():
    for name in ("tight", "exists"):
        ep = step(StubPolicy(), name)
        assert ep.workers == 0
        assert ep.action != "PROPOSE_CHANNEL"
        assert ep.illegal is False


def test_trained_head_illegal_not_worse_than_stub():
    report = compare_to_stub()
    assert report["stub"]["mean_workers"] == 0
    assert report["learned"]["mean_workers"] == 0
    assert report["illegal_not_worse"] is True
    assert report["workers_not_worse"] is True
    assert report["learned"]["illegal_rate"] == 0


def test_train_preserves_invariants():
    pol, ev = train(40)
    assert isinstance(pol, ImitationPolicy)
    assert ev["mean_workers"] == 0
    tight = step(pol, "tight")
    exists = step(pol, "exists")
    assert tight.action != "PROPOSE_CHANNEL"
    assert exists.action != "PROPOSE_CHANNEL"
    assert tight.workers == 0
    assert exists.workers == 0
