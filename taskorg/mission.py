from __future__ import annotations

import time
from dataclasses import dataclass, field

from .errors import InvariantError
from .models import (
    AXES,
    GATE_ORDER,
    HEAD_RESPONSES,
    MAX_WORKERS,
    NETS,
    QUAL_TOOLS,
    Artifact,
    Cue,
    Delta,
    FiveWH,
    GateRecord,
    NoteStatus,
    Slot,
    Status,
    WhyNote,
)


@dataclass
class LogEntry:
    event: str
    detail: dict
    ts: float = 0.0

    def __post_init__(self):
        if not self.ts:
            self.ts = time.time()


@dataclass
class Mission:
    id: str
    picture: FiveWH
    notes: dict[str, WhyNote] = field(default_factory=dict)
    cues: dict[str, Cue] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)
    deltas: list[Delta] = field(default_factory=list)
    open_nets: list[str] = field(default_factory=lambda: ["element", "up"])
    log: list[LogEntry] = field(default_factory=list)
    status: Status = Status.ACTIVE
    failed_stop_rules: list[str] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    budget: object | None = None
    stop_reason: str = ""
    last_verify: dict | None = None
    who_open: list[str] = field(default_factory=list)
    adapter_name: str = ""
    world: object | None = None

    def attach_budget(self, budget) -> None:
        self.budget = budget
        self._record("budget", {
            "max_calls": budget.max_calls,
            "max_tokens": budget.max_tokens,
            "max_seconds": budget.max_seconds,
        })

    def halt(self, reason: str) -> None:
        self.stop_reason = reason
        self.abort()
        self._record("halt", {"reason": reason})
        raise InvariantError("BUDGET", reason)

    def assert_running(self) -> None:
        if self.status in (Status.COMPLETE, Status.ABORT):
            raise InvariantError("BUDGET", f"mission already {self.status.value}: {self.stop_reason}")
        b = self.budget
        if b is None:
            return
        calls = len(self.calls)
        tokens = sum((c.get("prompt_tokens") or 0) + (c.get("completion_tokens") or 0) for c in self.calls)
        if calls >= b.max_calls:
            self.halt(f"max_calls {b.max_calls} reached")
        if tokens >= b.max_tokens:
            self.halt(f"max_tokens {b.max_tokens} reached")
        if b.elapsed() >= b.max_seconds:
            self.halt(f"max_seconds {b.max_seconds} reached")

    def record_call(self, call: dict) -> None:
        self.calls.append(call)
        self._record(
            "call",
            {k: call[k] for k in ("slot", "channel", "latency_s", "prompt_tokens", "completion_tokens") if k in call},
        )

    def __post_init__(self):
        if not any(s.function == "head" and s.id == self.picture.who_head_id for s in self.picture.slots):
            raise InvariantError("WHO", "Head slot missing from Who")
        if not self.who_open:
            self.who_open = [s.id for s in self.picture.slots]
        self._record("mission_open", {"id": self.id, "who": list(self.who_open)})

    def _record(self, event: str, detail: dict) -> None:
        self.log.append(LogEntry(event, detail))

    def _merge_picture(self, mark: str) -> None:
        mark = mark.strip()
        if not mark:
            return
        cur = (self.picture.current_picture or "").strip()
        if not cur or cur == mark:
            self.picture.current_picture = mark
            return
        if mark in cur:
            return
        self.picture.current_picture = f"{cur} | {mark}"

    def open_why_ids(self) -> list[str]:
        return [n.id for n in self.notes.values() if n.status == NoteStatus.OPEN]

    def write_who(self, actor_id: str, new_slots: list[Slot], *, gates: GateRecord | None = None, human_override: bool = False) -> None:
        self.assert_running()
        if actor_id != self.picture.who_head_id and not human_override:
            raise InvariantError("INV-1", "only Head.write_who or a logged human override may change Who")
        if human_override:
            self._record("human_override_who", {"actor": actor_id})

        old_workers = {s.id for s in self.picture.slots if s.function == "worker"}
        new_workers = [s for s in new_slots if s.function == "worker"]
        added = [s for s in new_workers if s.id not in old_workers]

        if len(new_workers) > MAX_WORKERS:
            raise InvariantError("CAP", f"worker cap is {MAX_WORKERS}")

        if added:
            if len(added) > 1:
                raise InvariantError("INV-8", "one write_who adds at most one Worker; one channel, one gate record")
            if gates is None:
                raise InvariantError("INV-8", "adding a Worker requires a three-gate record")
            if gates.order != GATE_ORDER:
                raise InvariantError("INV-9", "gate order violation")
            gates.assert_legal()
            for s in added:
                if not s.channel_id:
                    raise InvariantError("GATE-3", "new Worker needs a channel_id")
                if gates.channel_id and s.channel_id != gates.channel_id:
                    raise InvariantError("GATE-3", "Worker channel must match the gate channel")
            self._record(
                "split",
                {
                    "gates": {
                        "can_someone_else": gates.can_someone_else,
                        "should_we": gates.should_we,
                        "could_we": gates.could_we,
                        "named_failure": gates.named_failure,
                        "channel_id": gates.channel_id,
                        "order": list(gates.order),
                    },
                    "added": [s.id for s in added],
                },
            )

        heads = [s for s in new_slots if s.function == "head"]
        if len(heads) != 1:
            raise InvariantError("WHO", "exactly one Head")
        self.picture.slots = list(new_slots)
        self.picture.who_head_id = heads[0].id
        self._record("write_who", {"actor": actor_id, "slots": [s.id for s in new_slots]})

    def worker_spawn(self, actor_id: str, new_worker: Slot) -> None:
        raise InvariantError("INV-2", f"{actor_id} cannot spawn; Workers have no spawn primitive")

    def slide(self, actor_id: str, slot_id: str, skill: str, brief: str) -> None:
        if actor_id != self.picture.who_head_id:
            raise InvariantError("INV-1", "only Head may activate a skill")
        slot = self.picture.slot(slot_id)
        if slot.function == "why":
            raise InvariantError("INV-11", "Review is a voice, not a skill identity")
        if skill not in QUAL_TOOLS and skill not in ("execute", "retrieve", "reason", "draft", "simulate", "observe", "verify"):
            raise InvariantError("INV-11", f"unknown skill: {skill}")
        slot.skill = skill
        slot.tools = list(QUAL_TOOLS.get(skill, ["write"]))
        self._record("slide", {"slot": slot_id, "skill": skill, "brief": brief, "tools": list(slot.tools)})

    def assert_tools(self, slot_id: str, requested: list[str]) -> None:
        allowed = set(self.picture.slot(slot_id).tools)
        extra = [t for t in requested if t not in allowed]
        if extra:
            raise InvariantError("TOOLS", f"{slot_id} requested {extra}; allowlist is {sorted(allowed)}")

    def update_context(self, actor_id: str, picture_update: str, *, used_existing_observe: bool = True) -> None:
        if actor_id != self.picture.who_head_id:
            raise InvariantError("INV-1", "only Head may update Where")
        if not self.picture.step_off_picture:
            self.picture.step_off_picture = self.picture.current_picture
        self.picture.current_picture = picture_update
        self.picture.context_sufficient = True
        self._record(
            "look",
            {"actor": actor_id, "used_existing_observe": used_existing_observe, "picture": picture_update},
        )

    def request_recon_spawn(self, actor_id: str, new_worker: Slot, gates: GateRecord) -> None:
        if self.picture.context_sufficient:
            raise InvariantError("INV-10", "already see the other side — do not spawn to recon")
        has_observe = any(s.skill == "observe" for s in self.picture.slots)
        if has_observe:
            raise InvariantError("INV-10", "observe skill already on the team — inspect first, do not spawn")
        self.write_who(actor_id, self.picture.slots + [new_worker], gates=gates)

    def submit_why(self, body: str, note_id: str, kind: str = "why") -> WhyNote:
        note = WhyNote(id=note_id, body=body, kind=kind)
        self.notes[note_id] = note
        self._record("why_submit", {"id": note_id, "kind": kind})
        return note

    def report_plan_wrong(self, body: str, note_id: str = "plan-wrong") -> WhyNote:
        self.post_delta(
            Delta(
                claim=body,
                evidence=["plan-wrong"],
                uncertainty="scheme invalid",
                channel_id="up",
                net="up",
            )
        )
        return self.submit_why(body, note_id, kind="plan_wrong")

    def why_seize_command(self, note_id: str) -> None:
        raise InvariantError("WHY", "Why may not change Who, freeze the loop, or rewrite What")

    def why_halt(self) -> None:
        raise InvariantError("WHY", "Why may not freeze execution")

    def respond_why(self, actor_id: str, note_id: str, response: str, reason: str = "") -> None:
        if actor_id != self.picture.who_head_id:
            raise InvariantError("INV-3", "only Head.respond may close a Why note")
        if response not in HEAD_RESPONSES:
            raise InvariantError("WHY", f"response must be one of {HEAD_RESPONSES}")
        note = self.notes[note_id]
        if note.kind == "plan_wrong" and response not in ("CHANGE_METHOD", "REVISE_GOAL"):
            raise InvariantError(
                "INV-14",
                "plan-wrong cannot be answered with KEEP_ROSTER or DEFER; change the vector",
            )
        if note.kind == "plan_wrong" and not reason.strip():
            raise InvariantError("INV-14", "plan-wrong answer must name the new vector or purpose")
        note.response = response
        note.reason = reason
        if response == "DEFER":
            if not reason.strip():
                raise InvariantError("INV-4", "DEFER requires a recorded reason")
            note.status = NoteStatus.DEFERRED
        else:
            note.status = NoteStatus.CLOSED
        if response == "CHANGE_METHOD" and reason:
            self.picture.method = reason
        if response == "REVISE_GOAL" and reason:
            self.picture.purpose = reason
        self._record("why_respond", {"id": note_id, "response": response, "reason": reason})

    def picture_moved(self) -> bool:
        a = (self.picture.step_off_picture or "").strip()
        b = (self.picture.current_picture or "").strip()
        return bool(a and b and a != b)

    def ask_if_picture_moved(self, body: str = "Picture moved. Does purpose still hold?") -> WhyNote | None:
        if not self.picture_moved():
            return None
        if "why-picture" in self.notes:
            return self.notes["why-picture"]
        return self.submit_why(body, "why-picture")

    def send_out(self, actor_id: str, claim: str) -> None:
        self.write_net(actor_id, "out")
        self.post_delta(
            Delta(
                claim=claim,
                evidence=["out-net"],
                uncertainty="operator not in this graph",
                channel_id="out",
                net="out",
            )
        )

    def receive_adjacent(self, peer_id: str, claim: str) -> None:
        if "adjacent" not in self.open_nets:
            self.open_nets.append("adjacent")
        self.deltas.append(
            Delta(
                claim=claim,
                evidence=["adjacent-in", peer_id],
                uncertainty="peer picture stays theirs",
                channel_id=peer_id,
                net="adjacent",
            )
        )
        self._record("adjacent_in", {"peer": peer_id, "claim": claim})

    def send_adjacent(self, actor_id: str, claim: str, peer_id: str = "adjacent") -> None:
        self.write_net(actor_id, "adjacent")
        self.post_delta(
            Delta(
                claim=claim,
                evidence=["adjacent-net", peer_id],
                uncertainty="peer picture not merged here",
                channel_id=peer_id,
                net="adjacent",
            )
        )

    def write_net(self, actor_id: str, net: str) -> None:
        if actor_id != self.picture.who_head_id:
            raise InvariantError("INV-13", "only Head may open a net")
        if net not in NETS:
            raise InvariantError("INV-13", f"unknown net: {net}")
        if net not in self.open_nets:
            self.open_nets.append(net)
        self._record("write_net", {"net": net})

    def post_delta(self, delta: Delta) -> None:
        if delta.net not in self.open_nets:
            raise InvariantError("INV-13", f"net {delta.net} is not open")
        self.deltas.append(delta)
        if delta.net == "element" and delta.claim:
            self._merge_picture(delta.claim)
        self._record("delta", {"net": delta.net, "channel": delta.channel_id, "claim": delta.claim})

    def accept_artifact(self, artifact: Artifact) -> None:
        from .schema import validate_artifact

        validate_artifact(artifact)
        self.artifacts.append(artifact)
        if artifact.delta_to_picture:
            self._merge_picture(artifact.delta_to_picture)
        self._record("artifact", {"channel": artifact.channel_id, "claim": artifact.claim})

    def mark_stop_rule_failed(self, field: str) -> None:
        self.failed_stop_rules.append(field)
        self._record("stop_rule_failed", {"field": field})

    def verifier_pass_with_failed_stop(self) -> None:
        raise InvariantError("INV-5", "Verifier cannot pass an artifact that fails a stop-rule field")

    def mint_cue(self, cue: Cue) -> None:
        if not cue.expiry:
            raise InvariantError("CUE", "cue expiry is required")
        self.cues[cue.id] = cue
        self._record("cue_mint", {"id": cue.id, "trigger": cue.trigger, "target": cue.target})

    def dump_unscoped_history_into_brief(self) -> None:
        raise InvariantError("INV-6", "Memory cannot inject unscoped history into a Worker brief")

    def set_how(self, actor_id: str, method: str, axes: list[str]) -> None:
        if actor_id != self.picture.who_head_id:
            raise InvariantError("HOW", "only Head selects How")
        for a in axes:
            if a not in AXES:
                raise InvariantError("HOW", f"unknown axis: {a}")
        self.picture.method = method
        self.picture.axes = list(axes)
        self._record("set_how", {"method": method, "axes": axes})

    def complete(self) -> None:
        if any(n.kind == "plan_wrong" and n.status == NoteStatus.OPEN for n in self.notes.values()):
            raise InvariantError("INV-14", "COMPLETE illegal while a plan-wrong report is unanswered")
        if self.open_why_ids():
            raise InvariantError("INV-4", "COMPLETE illegal while a Why note is open; DEFER or answer first")
        if self.failed_stop_rules:
            raise InvariantError("INV-5", "COMPLETE illegal with a failed stop-rule field")
        from .schema import validate_five_wh

        validate_five_wh(self.picture)
        self.status = Status.COMPLETE
        self._record(
            "complete",
            {
                "channel_count": len({s.channel_id for s in self.picture.slots if s.channel_id}),
                "worker_count": self.picture.worker_count(),
                "could_this_have_been_one": self.picture.worker_count() == 0,
                "axes": list(self.picture.axes),
                "context_sufficient": self.picture.context_sufficient,
            },
        )

    def abort(self) -> None:
        self.status = Status.ABORT
        self._record("abort", {})

    def summary(self) -> dict:
        splits = [e for e in self.log if e.event == "split"]
        return {
            "id": self.id,
            "status": self.status.value,
            "slots": [s.id for s in self.picture.slots],
            "workers": self.picture.worker_count(),
            "channels": [s.channel_id for s in self.picture.slots if s.channel_id],
            "could_this_have_been_one": self.picture.worker_count() == 0,
            "splits": [e.detail for e in splits],
            "open_why": self.open_why_ids(),
            "looked_through_door": self.picture.context_sufficient,
            "how_axes": list(self.picture.axes),
            "method": self.picture.method,
            "step_off": self.picture.step_off_picture,
            "plan_wrong_open": any(
                n.kind == "plan_wrong" and n.status == NoteStatus.OPEN for n in self.notes.values()
            ),
        }
