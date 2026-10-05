from __future__ import annotations

import time
from dataclasses import dataclass, field

from .errors import InvariantError
from .models import (
    AXES,
    GATE_ORDER,
    LEAD_RESPONSES,
    MAX_WORKERS,
    STREAMS,
    SKILL_TOOLS,
    Artifact,
    Cue,
    Delta,
    RunState,
    GateRecord,
    NoteStatus,
    Slot,
    Status,
    ReviewNote,
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
class Run:
    id: str
    state: RunState
    notes: dict[str, ReviewNote] = field(default_factory=dict)
    cues: dict[str, Cue] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)
    deltas: list[Delta] = field(default_factory=list)
    open_streams: list[str] = field(default_factory=lambda: ["merge", "escalate"])
    log: list[LogEntry] = field(default_factory=list)
    status: Status = Status.ACTIVE
    failed_stop_rules: list[str] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    budget: object | None = None
    stop_reason: str = ""
    last_verify: dict | None = None
    roster_at_start: list[str] = field(default_factory=list)
    adapter_name: str = ""
    world: object | None = None

    def attach_budget(self, budget) -> None:
        self.budget = budget
        self._record("budget", {
            "max_calls": budget.max_calls,
            "max_tokens": budget.max_tokens,
            "max_seconds": budget.max_seconds,
        })

    def halt(self, reason: str, code: str = "BUDGET") -> None:
        self.stop_reason = reason
        if self.status != Status.ABORT:
            self.abort()
        self._record("halt", {"reason": reason, "code": code})
        raise InvariantError(code, reason)

    def usage(self) -> tuple[int, int]:
        tokens = sum((c.get("prompt_tokens") or 0) + (c.get("completion_tokens") or 0) for c in self.calls)
        return len(self.calls), tokens

    def assert_running(self) -> None:
        """Before a call: is there room for one more?"""
        if self.status in (Status.COMPLETE, Status.ABORT):
            raise InvariantError("BUDGET", f"run already {self.status.value}: {self.stop_reason}")
        b = self.budget
        if b is None:
            return
        calls, tokens = self.usage()
        if calls >= b.max_calls:
            self.halt(f"max_calls {b.max_calls} reached")
        if tokens >= b.max_tokens:
            self.halt(f"max_tokens {b.max_tokens} reached")
        if b.elapsed() >= b.max_seconds:
            self.halt(f"max_seconds {b.max_seconds} reached")

    def assert_within_budget(self) -> None:
        """After a call: did it overrun? Spending the last unit of budget is legal."""
        b = self.budget
        if b is None:
            return
        calls, tokens = self.usage()
        if calls > b.max_calls:
            self.halt(f"max_calls {b.max_calls} exceeded")
        if tokens > b.max_tokens:
            self.halt(f"max_tokens {b.max_tokens} exceeded ({tokens})")
        if b.elapsed() > b.max_seconds:
            self.halt(f"max_seconds {b.max_seconds} exceeded")

    def record_call(self, call: dict) -> None:
        self.calls.append(call)
        self._record(
            "call",
            {k: call[k] for k in ("slot", "channel", "latency_s", "prompt_tokens", "completion_tokens") if k in call},
        )

    def __post_init__(self):
        if not any(s.function == "lead" and s.id == self.state.lead_id for s in self.state.slots):
            raise InvariantError("ROSTER", "the lead slot is missing from the roster")
        if not self.roster_at_start:
            self.roster_at_start = [s.id for s in self.state.slots]
        self._record("run_open", {"id": self.id, "roster": list(self.roster_at_start)})

    def _record(self, event: str, detail: dict) -> None:
        self.log.append(LogEntry(event, detail))

    def _assert_open(self) -> None:
        """A completed or aborted board is a record. Nothing on it changes."""
        if self.status in (Status.COMPLETE, Status.ABORT):
            raise InvariantError("CLOSED", f"run is {self.status.value}; the board is a record now")

    def _merge_context(self, mark: str) -> None:
        mark = mark.strip()
        if not mark:
            return
        cur = (self.state.context or "").strip()
        if not cur or cur == mark:
            self.state.context = mark
            return
        if mark in cur:
            return
        self.state.context = f"{cur} | {mark}"

    def open_review_ids(self) -> list[str]:
        return [n.id for n in self.notes.values() if n.status == NoteStatus.OPEN]

    # --- Roster ---

    def set_roster(self, actor_id: str, new_slots: list[Slot], *, gates: GateRecord | None = None, human_override: bool = False) -> None:
        """INV-1. Only the lead, or a logged human override, changes the roster.

        Everything is validated before the split is logged or the roster is written,
        so a refused change leaves no trace on the board.
        """
        self.assert_running()
        if actor_id != self.state.lead_id and not human_override:
            raise InvariantError("INV-1", "only the lead or a logged human override may change the roster")
        if human_override:
            self._record("human_override_roster", {"actor": actor_id})

        ids = [s.id for s in new_slots]
        if len(ids) != len(set(ids)):
            raise InvariantError("ROSTER", "slot ids must be unique")
        leads = [s for s in new_slots if s.function == "lead"]
        if len(leads) != 1:
            raise InvariantError("ROSTER", "the roster needs exactly one lead")

        # A Worker is new if its id is new or it was re-tasked to another channel.
        old_workers = {s.id: s.channel_id for s in self.state.slots if s.function == "worker"}
        new_workers = [s for s in new_slots if s.function == "worker"]
        added = [s for s in new_workers if s.id not in old_workers or old_workers[s.id] != s.channel_id]

        if len(new_workers) > MAX_WORKERS:
            raise InvariantError("CAP", f"worker cap is {MAX_WORKERS}")

        if added:
            if len(added) > 1:
                raise InvariantError("INV-8", "one set_roster adds at most one Worker; one channel, one gate record")
            if gates is None:
                raise InvariantError("INV-8", "adding or re-tasking a Worker requires a three-gate record")
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

        self.state.slots = list(new_slots)
        self.state.lead_id = leads[0].id
        self._record("set_roster", {"actor": actor_id, "slots": [s.id for s in new_slots]})

    def worker_spawn(self, actor_id: str, new_worker: Slot) -> None:
        """INV-2. Workers have no spawn primitive — this method exists to fail."""
        raise InvariantError("INV-2", f"{actor_id} cannot spawn; Workers have no spawn primitive")

    # --- Slide (skill activation) ---

    def switch_skill(self, actor_id: str, slot_id: str, skill: str, brief: str) -> None:
        """INV-11. Skill activation is a brief-and-tools change, not a new identity."""
        self._assert_open()
        if actor_id != self.state.lead_id:
            raise InvariantError("INV-1", "only the lead may switch a skill")
        slot = self.state.slot(slot_id)
        if slot.function == "reviewer":
            raise InvariantError("INV-11", "the reviewer raises concerns; it does not take a skill")
        if skill not in SKILL_TOOLS:
            raise InvariantError("INV-11", f"unknown skill: {skill}")
        slot.skill = skill
        slot.tools = list(SKILL_TOOLS.get(skill, ["write"]))
        self._record("switch_skill", {"slot": slot_id, "skill": skill, "brief": brief, "tools": list(slot.tools)})

    def assert_tools(self, slot_id: str, requested: list[str]) -> None:
        allowed = set(self.state.slot(slot_id).tools)
        extra = [t for t in requested if t not in allowed]
        if extra:
            raise InvariantError("TOOLS", f"{slot_id} requested {extra}; allowlist is {sorted(allowed)}")

    # --- Context ---

    def update_context(self, actor_id: str, new_context: str, *, used_existing_observe: bool = True) -> None:
        """Update the shared context without starting a sub-agent. INV-10."""
        self._assert_open()
        if actor_id != self.state.lead_id:
            raise InvariantError("INV-1", "only the lead may update the context")
        if not self.state.initial_context:
            self.state.initial_context = self.state.context
        self.state.context = new_context
        self.state.context_sufficient = True
        self._record(
            "context",
            {"actor": actor_id, "used_existing_observe": used_existing_observe, "context": new_context},
        )

    def request_exploratory_spawn(self, actor_id: str, new_worker: Slot, gates: GateRecord) -> None:
        """INV-10. Illegal if context is enough or an observe skill exists."""
        if self.state.context_sufficient:
            raise InvariantError("INV-10", "the context is already sufficient; do not start a sub-agent just to look")
        has_observe = any(s.skill == "observe" for s in self.state.slots)
        if has_observe:
            raise InvariantError("INV-10", "someone on the roster already has the observe skill; look first, do not start a sub-agent")
        self.set_roster(actor_id, self.state.slots + [new_worker], gates=gates)

    # --- Reviews ---

    def open_review(self, body: str, note_id: str, kind: str = "review") -> ReviewNote:
        self._assert_open()
        # Ids are single-use: reusing one would overwrite a note, and with it an open replan report.
        if note_id in self.notes:
            raise InvariantError("REVIEW", f"note id already used: {note_id}")
        note = ReviewNote(id=note_id, body=body, kind=kind)
        self.notes[note_id] = note
        self._record("review_open", {"id": note_id, "kind": kind})
        return note

    def request_replan(self, body: str, note_id: str = "replan") -> ReviewNote:
        """INV-14. Escalate: the method no longer fits the context."""
        if note_id in self.notes:
            raise InvariantError("REVIEW", f"note id already used: {note_id}")
        self.post_delta(
            Delta(
                claim=body,
                evidence=["replan"],
                uncertainty="scheme invalid",
                channel_id="escalate",
                stream="escalate",
            )
        )
        return self.open_review(body, note_id, kind="replan")

    def reviewer_take_over(self, note_id: str) -> None:
        """Exists to fail. The reviewer cannot change the roster or halt the run."""
        raise InvariantError("REVIEW", "the reviewer may not change the roster, freeze the run, or rewrite the goal")

    def reviewer_halt(self) -> None:
        raise InvariantError("REVIEW", "the reviewer may not freeze the run")

    def answer_review(self, actor_id: str, note_id: str, response: str, reason: str = "") -> None:
        self._assert_open()
        if actor_id != self.state.lead_id:
            raise InvariantError("INV-3", "only the lead may answer a review")
        if response not in LEAD_RESPONSES:
            raise InvariantError("REVIEW", f"response must be one of {LEAD_RESPONSES}")
        note = self.notes.get(note_id)
        if note is None:
            raise InvariantError("REVIEW", f"unknown note: {note_id}")
        if note.kind == "replan" and response not in ("CHANGE_METHOD", "REVISE_GOAL"):
            raise InvariantError(
                "INV-14",
                "a replan request cannot be answered with KEEP_ROSTER or DEFER; change the method",
            )
        if note.kind == "replan" and not reason.strip():
            raise InvariantError("INV-14", "a replan answer must name the new method or purpose")
        if response == "DEFER" and not reason.strip():
            raise InvariantError("INV-4", "DEFER requires a recorded reason")
        note.response = response
        note.reason = reason
        if response == "DEFER":
            note.status = NoteStatus.DEFERRED
        else:
            note.status = NoteStatus.CLOSED
        if response == "CHANGE_METHOD" and reason:
            self.state.method = reason
        if response == "REVISE_GOAL" and reason:
            self.state.purpose = reason
        self._record("review_answer", {"id": note_id, "response": response, "reason": reason})

    # --- Artifacts / verify ---

    def context_changed(self) -> bool:
        a = (self.state.initial_context or "").strip()
        b = (self.state.context or "").strip()
        return bool(a and b and a != b)

    def review_if_context_changed(self, body: str = "The context changed. Does the purpose still hold?") -> ReviewNote | None:
        if not self.context_changed():
            return None
        if "context-changed" in self.notes:
            return self.notes["context-changed"]
        return self.open_review(body, "context-changed")

    def report_out(self, actor_id: str, claim: str) -> None:
        """Typed report to the operator. Does not change the roster."""
        self.open_stream(actor_id, "report")
        self.post_delta(
            Delta(
                claim=claim,
                evidence=["report-stream"],
                uncertainty="operator not in this graph",
                channel_id="report",
                stream="report",
            )
        )

    def receive_peer(self, peer_id: str, claim: str) -> None:
        """Inbound from a peer run. Logged. Not merged into our context or roster."""
        self._assert_open()
        if "peer" not in self.open_streams:
            self.open_streams.append("peer")
        self.deltas.append(
            Delta(
                claim=claim,
                evidence=["peer-in", peer_id],
                uncertainty="the peer's context stays theirs",
                channel_id=peer_id,
                stream="peer",
            )
        )
        self._record("peer_in", {"peer": peer_id, "claim": claim})

    def send_peer(self, actor_id: str, claim: str, peer_id: str = "peer") -> None:
        """Typed update to a peer run. Our context and roster stay ours."""
        self.open_stream(actor_id, "peer")
        self.post_delta(
            Delta(
                claim=claim,
                evidence=["peer-stream", peer_id],
                uncertainty="the peer's context is not merged here",
                channel_id=peer_id,
                stream="peer",
            )
        )

    def open_stream(self, actor_id: str, stream: str) -> None:
        self._assert_open()
        if actor_id != self.state.lead_id:
            raise InvariantError("INV-13", "only the lead may open a stream")
        if stream not in STREAMS:
            raise InvariantError("INV-13", f"unknown stream: {stream}")
        if stream not in self.open_streams:
            self.open_streams.append(stream)
        self._record("open_stream", {"stream": stream})

    def post_delta(self, delta: Delta) -> None:
        self._assert_open()
        if delta.stream not in self.open_streams:
            raise InvariantError("INV-13", f"stream {delta.stream} is not open")
        self.deltas.append(delta)
        if delta.stream == "merge" and delta.claim:
            self._merge_context(delta.claim)
        self._record("delta", {"stream": delta.stream, "channel": delta.channel_id, "claim": delta.claim})

    def accept_artifact(self, artifact: Artifact) -> None:
        self._assert_open()
        from .schema import validate_artifact

        validate_artifact(artifact)
        self.artifacts.append(artifact)
        if artifact.context_update:
            self._merge_context(artifact.context_update)
        self._record("artifact", {"channel": artifact.channel_id, "claim": artifact.claim})

    def mark_stop_rule_failed(self, field: str) -> None:
        self._assert_open()
        self.failed_stop_rules.append(field)
        self._record("stop_rule_failed", {"field": field})

    def verifier_pass_with_failed_stop(self) -> None:
        raise InvariantError("INV-5", "Verifier cannot pass an artifact that fails a stop-rule field")

    # --- Memory ---

    def mint_cue(self, cue: Cue) -> None:
        self._assert_open()
        if not cue.expiry:
            raise InvariantError("CUE", "cue expiry is required")
        self.cues[cue.id] = cue
        self._record("cue_mint", {"id": cue.id, "trigger": cue.trigger, "target": cue.target})

    def dump_unscoped_history_into_brief(self) -> None:
        raise InvariantError("INV-6", "Memory cannot inject unscoped history into a Worker brief")

    # --- Method ---

    def set_method(self, actor_id: str, method: str, axes: list[str]) -> None:
        self._assert_open()
        if actor_id != self.state.lead_id:
            raise InvariantError("METHOD", "only the lead sets the method")
        for a in axes:
            if a not in AXES:
                raise InvariantError("METHOD", f"unknown axis: {a}")
        self.state.method = method
        self.state.axes = list(axes)
        self._record("set_method", {"method": method, "axes": axes})

    # --- Complete ---

    def complete(self) -> None:
        self._assert_open()
        if any(n.kind == "replan" and n.status == NoteStatus.OPEN for n in self.notes.values()):
            raise InvariantError("INV-14", "cannot complete while a replan request is unanswered")
        if self.open_review_ids():
            raise InvariantError("INV-4", "cannot complete while a review is open; answer or defer it first")
        if self.failed_stop_rules:
            raise InvariantError("INV-5", "cannot complete with a failed stop-rule check")
        from .schema import validate_state

        validate_state(self.state)
        self.status = Status.COMPLETE
        self._record(
            "complete",
            {
                "channel_count": len({s.channel_id for s in self.state.slots if s.channel_id}),
                "worker_count": self.state.worker_count(),
                "could_this_have_been_one": self.state.worker_count() == 0,
                "axes": list(self.state.axes),
                "context_sufficient": self.state.context_sufficient,
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
            "slots": [s.id for s in self.state.slots],
            "workers": self.state.worker_count(),
            "channels": [s.channel_id for s in self.state.slots if s.channel_id],
            "could_this_have_been_one": self.state.worker_count() == 0,
            "splits": [e.detail for e in splits],
            "open_reviews": self.open_review_ids(),
            "context_checked": self.state.context_sufficient,
            "axes": list(self.state.axes),
            "method": self.state.method,
            "initial_context": self.state.initial_context,
            "replan_open": any(
                n.kind == "replan" and n.status == NoteStatus.OPEN for n in self.notes.values()
            ),
        }
