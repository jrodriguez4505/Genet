"""Invariant fuzzing: random calls from random actors against the mission graph.

Whatever the sequence, after every call:

- there is exactly one lead, and slot ids are unique
- workers never exceed the cap, and every worker on the roster has a legal
  three-gate record for its exact channel
- a refused call leaves the roster and the split log untouched
- only the lead (or a logged human override) ever changes the roster
- an open plan-wrong report is closed only by changing method or goal
- a completed mission has no open review note and no failed stop rule
- a closed mission's roster never changes again
- the API only ever fails with InvariantError, never a stray KeyError
"""

import random

import pytest

from taskorg.errors import InvariantError
from taskorg.factory import element_at_rest
from taskorg.models import AXES, GATE_ORDER, HEAD_RESPONSES, MAX_WORKERS, NETS, QUALS, Cue, Delta, GateRecord, NoteStatus, Slot

CHANNELS = ["a", "b", "c", "d", "e", None]
WORKER_IDS = ["w-a", "w-b", "w-c", "w-d", "w-e", "memory-1"]
NOTE_IDS = ["n1", "n2", "plan-wrong", "why-1", "ghost"]


def roster(m):
    return [(s.id, s.function, s.channel_id) for s in m.picture.slots]


def splits(m):
    return [e for e in m.log if e.event == "split"]


def legal_record(rng, channel):
    return GateRecord(False, True, "independent part", True, channel, GATE_ORDER)


def any_record(rng, channel):
    if rng.random() < 0.5:
        return legal_record(rng, channel)
    order = list(GATE_ORDER)
    if rng.random() < 0.3:
        rng.shuffle(order)
    return GateRecord(
        can_someone_else=rng.random() < 0.3,
        should_we=rng.random() < 0.8,
        named_failure=rng.choice(["x", "", None]),
        could_we=rng.random() < 0.8,
        channel_id=rng.choice(CHANNELS),
        order=tuple(order),
    )


def mutated_slots(rng, m):
    slots = list(m.picture.slots)
    kind = rng.choice(["add", "add", "remove", "retask", "second_head", "drop_head", "dup", "same"])
    if kind == "add":
        slots.append(Slot(id=rng.choice(WORKER_IDS), function="worker", channel_id=rng.choice(CHANNELS)))
    elif kind == "remove" and len(slots) > 1:
        slots.pop(rng.randrange(len(slots)))
    elif kind == "retask":
        workers = [i for i, s in enumerate(slots) if s.function == "worker"]
        if workers:
            i = rng.choice(workers)
            slots[i] = Slot(id=slots[i].id, function="worker", channel_id=rng.choice(CHANNELS))
    elif kind == "second_head":
        slots.append(Slot(id="head-2", function="head"))
    elif kind == "drop_head":
        slots = [s for s in slots if s.function != "head"]
    elif kind == "dup":
        slots.append(slots[0])
    return slots


def random_op(rng, m):
    head = m.picture.who_head_id
    actor = rng.choice([head, head, head, "w-a", "verifier-1", "why-1", "stranger"])
    ids = [s.id for s in m.picture.slots] + ["ghost"]
    op = rng.choice([
        "write_who", "write_who", "write_who", "slide", "update_context", "submit_why", "respond_why",
        "respond_why", "report_plan_wrong", "post_delta", "write_net", "set_how", "complete",
        "assert_tools", "recon", "mint_cue", "halt",
    ])
    # Closing ops are rare so sequences run deep before the board closes.
    if op == "halt" and rng.random() > 0.05:
        op = "update_context"
    if op == "complete" and rng.random() > 0.3:
        op = "write_who"
    override = op == "write_who" and rng.random() < 0.1
    calls = {
        "write_who": lambda: m.write_who(actor, mutated_slots(rng, m), gates=rng.choice([None, any_record(rng, rng.choice(CHANNELS))]) if rng.random() < 0.4 else _matching(rng, m), human_override=override),
        "slide": lambda: m.slide(actor, rng.choice(ids), rng.choice(QUALS + ("juggle",)), "fuzz"),
        "update_context": lambda: m.update_context(actor, rng.choice(["new picture", "other picture"])),
        "submit_why": lambda: m.submit_why("why?", rng.choice(NOTE_IDS), kind=rng.choice(["why", "why", "plan_wrong"])),
        "respond_why": lambda: m.respond_why(actor, rng.choice(NOTE_IDS), rng.choice(HEAD_RESPONSES + ("NOPE",)), rng.choice(["", "new method"])),
        "report_plan_wrong": lambda: m.report_plan_wrong("plan is dead", note_id=rng.choice(NOTE_IDS)),
        "post_delta": lambda: m.post_delta(Delta(claim="mark", evidence=[], uncertainty="", channel_id="x", net=rng.choice(NETS))),
        "write_net": lambda: m.write_net(actor, rng.choice(NETS + ("side",))),
        "set_how": lambda: m.set_how(actor, "method", rng.sample(AXES + ("sideways",), 2)),
        "complete": lambda: m.complete(),
        "assert_tools": lambda: m.assert_tools(rng.choice(ids), rng.sample(["write", "read", "spawn", "observe"], 2)),
        "recon": lambda: m.request_recon_spawn(actor, Slot(id="w-recon", function="worker", skill="observe", channel_id="recon"), legal_record(rng, "recon")),
        "mint_cue": lambda: m.mint_cue(Cue(id="c", trigger="t", payload="p", target=head, expiry=rng.choice(["", "mission-end"]))),
        "halt": lambda: m.halt("fuzz kill switch"),
    }
    return op, actor, override, calls[op]


def _matching(rng, m):
    """A legal record for whichever single worker the next write might add; often right, sometimes not."""
    return legal_record(rng, rng.choice(CHANNELS))


def check(m, before, op, actor, override, raised, plan_wrong_before):
    heads = [s for s in m.picture.slots if s.function == "head"]
    assert len(heads) == 1 and heads[0].id == m.picture.who_head_id
    ids = [s.id for s in m.picture.slots]
    assert len(ids) == len(set(ids))
    assert m.picture.worker_count() <= MAX_WORKERS
    recorded = {
        (sid, e.detail["gates"]["channel_id"])
        for e in splits(m)
        for sid in e.detail["added"]
        if not e.detail["gates"]["can_someone_else"] and e.detail["gates"]["should_we"] and e.detail["gates"]["could_we"]
    }
    for s in m.picture.slots:
        if s.function == "worker":
            assert (s.id, s.channel_id) in recorded, f"worker {s.id}@{s.channel_id} has no legal gate record"
    if raised:
        assert roster(m) == before["roster"], f"refused {op} changed the roster"
        assert len(splits(m)) == before["splits"], f"refused {op} logged a split"
    if roster(m) != before["roster"]:
        assert op in ("write_who", "recon") and (actor == before["head"] or override)
        assert before["status"] == "active"
    for note_id in plan_wrong_before:
        note = m.notes.get(note_id)
        assert note is not None and note.kind == "plan_wrong", f"open plan-wrong {note_id} was overwritten"
        if note.status != NoteStatus.OPEN:
            assert note.response in ("CHANGE_METHOD", "REVISE_GOAL")
    if m.status.value == "complete":
        assert not m.open_why_ids() and not m.failed_stop_rules


@pytest.mark.parametrize("seed", range(300))
def test_invariants_hold_under_random_calls(seed):
    rng = random.Random(seed)
    m = element_at_rest(f"fz-{seed}", "effect", "purpose", "end state")
    for _ in range(40):
        before = {"roster": roster(m), "splits": len(splits(m)), "head": m.picture.who_head_id, "status": m.status.value}
        plan_wrong_before = [n.id for n in m.notes.values() if n.kind == "plan_wrong" and n.status == NoteStatus.OPEN]
        op, actor, override, call = random_op(rng, m)
        raised = False
        try:
            call()
        except InvariantError:
            raised = True
        check(m, before, op, actor, override, raised, plan_wrong_before)
