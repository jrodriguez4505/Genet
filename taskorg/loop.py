from __future__ import annotations

import functools
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

from .adapters import TOOL_RESULTS, Brief, OperatorQuestion, ModelAdapter, StubAdapter
from . import checks, situation
from .budget import Budget
from .cues import fire_auto_cues
from .errors import InvariantError
from .gates import LEAD_COVERS, Assessment, Subtask, assess
from .memory_store import MemoryStore
from .run import Run
from .models import MAX_WORKERS, SKILL_TOOLS, SKILLS, Artifact, Delta, Slot, Status
from .subtasks import parse_proposals
from .review import team_review
from .tools import RUNNABLE, Toolbox, parse_request


def _criterion(token: str) -> re.Pattern:
    """A criterion as a whole word or number: "4.1" is not met by "14.1" or "4.15"."""
    left = r"(?<![\w.])" if token[0].isalnum() else ""
    right = r"(?![\w])" if token[-1].isalnum() else ""
    return re.compile(left + re.escape(token) + right)


def score_criteria(product: Artifact | None, criteria: list[str]) -> dict:
    """Criteria must show in the product. The Verifier cannot vouch for them by echo."""
    parts = []
    if product:
        parts.extend([product.claim, *product.evidence, product.context_update])
    blob = " ".join(parts).lower()
    hits, misses = [], []
    for raw in criteria:
        token = raw.strip().lower()
        if token and _criterion(token).search(blob):
            hits.append(raw)
        elif token:
            misses.append(raw)
    total = max(1, len([c for c in criteria if c.strip()]))
    return {"hits": hits, "misses": misses, "score": round(len(hits) / total, 3)}


def world_misses(run: Run, product: Artifact | None) -> list[str]:
    """Verifier looks at state, not only words."""
    misses = []
    if not (run.state.context or "").strip():
        misses.append("world: context is empty")
    if not (run.state.method or "").strip():
        misses.append("world: method is empty")
    if product is not None and not (product.claim or "").strip():
        misses.append("world: product claim empty")
    if run.state.worker_count() > 0:
        merged = [d for d in run.deltas if d.stream == "merge"]
        # A part whose sub-agent failed, or handed it back, is accounted for: the lead covered it.
        covered = any(e.event in ("part_failed", "part_reported") for e in run.log)
        if not merged and not covered:
            misses.append("world: workers exist but merged no results")
    if run.open_review_ids():
        misses.append("world: a review is still open")
    return misses


_VERDICT = re.compile(r"\s*(PASS|FAIL)(?:ED)?\b", re.IGNORECASE)


def verdict(claim: str) -> str:
    """PASS or FAIL when the claim leads with it, else "". "Passing this would be wrong" is not a pass,
    and "PASS: nothing failed" is not a fail."""
    m = _VERDICT.match(claim or "")
    return m.group(1).upper() if m else ""


# How much of a product's evidence the verifier reads: enough to judge its sources, bounded however long the reply.
REVIEW_EVIDENCE = 12
REVIEW_EVIDENCE_CHARS = 400


def _for_review(product: Artifact) -> str:
    """The product as the verifier reads it: the claim and the evidence given with it, which the kernel's own
    criteria check counts too. Shown the claim alone, a verifier failed sourced answers as unsourced."""
    shown = [e[:REVIEW_EVIDENCE_CHARS] for e in product.evidence[:REVIEW_EVIDENCE] if e.strip()]
    if not shown:
        return product.claim
    more = f"\n[{len(product.evidence) - REVIEW_EVIDENCE} more not shown]" if len(product.evidence) > REVIEW_EVIDENCE else ""
    return product.claim + "\nEVIDENCE GIVEN WITH IT\n" + "\n".join(f"- {e}" for e in shown) + more


def _verifier_accepts(check: Artifact, run: Run, product: Artifact | None = None) -> bool:
    if verdict(check.claim) != "PASS":
        scored = score_criteria(product, run.state.success_criteria)
        scored["world_misses"] = ["claim is not PASS"]
        run.last_verify = scored
        return False
    scored = score_criteria(product, run.state.success_criteria)
    w = world_misses(run, product)
    scored["world_misses"] = w
    run.last_verify = scored
    return scored["score"] >= 1.0 and not scored["misses"] and not w


@dataclass
class LoopResult:
    run: Run
    product: Artifact | None
    verified: bool
    operator_question: str | None
    lead_answer: str | None
    split: bool = False
    channels: list[str] | None = None
    verdicts: list[Assessment] | None = None


# Tool names the kernel recognizes in artifact.requests. Anything else is free text.
TOOL_NAMES = {"write", "verify", "observe", "read", "retrieve", "simulate", "spawn"}
# Shared ownership: a sub-agent's own bad reply, or one failed call to the model, is the team's to absorb.
# Its part goes back to the lead and the run goes on. Authority violations, budget halts and crashes
# still stop the run at once.
PART_FAILURES = ("SCHEMA", "LIVE")
# A malformed reply is asked again once, with this note. Only SCHEMA: an authority violation is never retried.
RETRY_NOTE = ("\nRETRY. Your last reply was not the JSON object the schema asks for. Reply with only that "
              "object: claim, evidence, uncertainty, channel_id, context_update and requests. Any other key is "
              "refused; what it held belongs in claim, which is the product.")
# Model output is untrusted. These bound what one reply can make the kernel do.
MAX_TOOL_REQUESTS = 8    # tools run per round; repeats count once
MAX_PROPOSALS = 16       # sub-tasks the gates consider from one plan
REPORT_REASON_CHARS = 200

# Reported up (team design part 8): with report_up on, a sub-agent may hand its part back with this request.
REPLAN_REQUEST = "replan:"
REPORT_UP_NOTE = (" If your part cannot be done as planned, because your files do not hold what it needs or the "
                  "plan is wrong for it, do not guess: add the request replan:REASON, and the lead takes the part back.")
# Kept current: what a member's next call says when the situation changed since its last one.
SITUATION_CHANGED = "SITUATION CHANGED since your last call: {fields}. The brief shows it as it stands now."

PLAN_BRIEF = (
    "PLAN. Decide how to staff this task. Default is a single agent: you do the work yourself. "
    "Propose a sub-agent only for a part of the work that is independent of the rest "
    "and should not share a context with it. For each, add one request in the form "
    "subtask:CHANNEL@SKILL=NAMED_FAILURE, for example subtask:north-region@retrieve=two_regions_figures_get_mixed. "
    "CHANNEL is a short name of letters, digits and hyphens, one per part: for a part that reads one file, "
    "that file's name without its extension. SKILL is one of {skills}. NAMED_FAILURE says what goes wrong if a "
    "single agent does it. "
    "A sub-agent that must search or read the workspace needs skill retrieve (or observe to list files). "
    "Propose nothing if a single agent is enough. The kernel judges the proposal; you do not change the roster. "
    "claim: your read of the situation in one or two sentences."
)


def _tool_name(request: str) -> str:
    return parse_request(request)[0]


def _reply_estimate(art: Artifact) -> int:
    """A reply's size when nobody reported it: everything the model wrote, not only its claim."""
    fields = [art.claim, art.evidence, art.uncertainty, art.channel_id, art.context_update, art.requests]
    return max(1, len(json.dumps(fields)) // 4)


def _reported(value) -> int | None:
    """A token count an adapter reports, if it is one: a whole number, not negative.
    Anything else is ignored and the kernel's estimate stands, so a reply cannot spend negative tokens."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _sibling_heard(run: Run, brief: Brief) -> list[str]:
    """Which sibling channels' products are visible anywhere in this worker's brief."""
    if brief.slot_function != "worker" or not brief.channel_id:
        return []
    worker_channels = {s.channel_id for s in run.state.slots if s.function == "worker" and s.channel_id}
    seen_text = f"{brief.packet}\n{brief.context}"
    heard = []
    for other in sorted(worker_channels - {brief.channel_id}):
        marks = [f"channel:{other}"]
        for art in run.artifacts:
            if art.channel_id == other:
                marks.extend(t for t in (art.claim, art.context_update) if len(t.strip()) >= 8)
        if any(m in seen_text for m in marks):
            heard.append(other)
    return heard


def _plan_wrong(art: Artifact) -> str | None:
    """The reason a sub-agent gave for handing its part back, or None. Model text: bounded, never a lesson."""
    for r in art.requests:
        text = r.strip()
        if text[:len(REPLAN_REQUEST)].lower() == REPLAN_REQUEST:
            return text[len(REPLAN_REQUEST):].strip()[:REPORT_REASON_CHARS] or "no reason given"
    return None


def _stop_reason(e: BaseException) -> str:
    return str(e) if isinstance(e, InvariantError) else f"{type(e).__name__}: {e}"


def _aborts_on_error(method):
    """A run that dies on anything, an invariant, a crash or Ctrl-C, leaves the board ABORT, not ACTIVE."""

    @functools.wraps(method)
    def wrapper(self, run: Run, *args, **kwargs):
        try:
            result = method(self, run, *args, **kwargs)
        except BaseException as e:
            self._abort(run, e)
            self._team_review(run, e)
            raise
        self._team_review(run, None)
        return result

    return wrapper


class Engine:
    """Graph owns authority. Adapter only fills artifacts.

    toolbox     sandboxed read-only tools for specialists (none attached by default)
    parallel    sub-agents call the model at the same time; their results are
                accepted in subtask order so the board is deterministic
    """

    # A split needs this many legal sub-tasks. Below it, a single agent does the work.
    min_split = 2

    def __init__(
        self,
        store: MemoryStore,
        adapter: ModelAdapter | None = None,
        budget: Budget | None = None,
        policy=None,
        *,
        toolbox: Toolbox | None = None,
        parallel: bool = True,
        max_tool_rounds: int = 2,
        split_policy: str = "measured",
        isolation_required: bool = False,
        fit_fraction: float = 0.5,
        lessons: bool = True,
        verify_view: str = "shared",
        verify_sources: str = "layered",
        verify_sample: int = checks.SAMPLE,
        report_up: bool = False,
    ):
        self.store = store
        self.adapter = adapter or StubAdapter()
        self.budget = budget or Budget()
        self.policy = policy
        self.toolbox = toolbox or Toolbox()
        self.parallel = parallel
        self.max_tool_rounds = max(0, int(max_tool_rounds))  # negative rounds would make a worker cost less than one call
        # "Should we" for the lead's proposals: "measured" needs declared isolation or
        # material that does not fit one context; "stated" accepts the lead's reasons.
        self.split_policy = split_policy
        self.isolation_required = isolation_required
        self.fit_fraction = fit_fraction
        # After a failed run, write its lessons to the shared guidelines every agent reads.
        self.lessons = lessons
        # What the verifier reads the product against (checks.py): its view, and the sources the kernel opens.
        if verify_view not in checks.VIEWS:
            raise ValueError(f"verify_view must be one of {checks.VIEWS}, got {verify_view!r}")
        if verify_sources not in checks.SOURCES:
            raise ValueError(f"verify_sources must be one of {checks.SOURCES}, got {verify_sources!r}")
        self.verify_view = verify_view
        self.verify_sources = verify_sources
        self.verify_sample = max(0, int(verify_sample))
        # A sub-agent may hand its part back when the plan is wrong for it. Off by default: it changes the sub-agent brief.
        self.report_up = report_up
        # Sub-agents run in threads; every run mutation in a call goes through this.
        self._lock = threading.RLock()
        # Calls started but not yet recorded, per run. Admission counts them, so parallel
        # sub-agents cannot each spend past the budget; _settled wakes calls waiting on them.
        self._settled = threading.Condition(self._lock)
        self._inflight: dict[int, int] = {}

    def _abort(self, run: Run, e: BaseException) -> None:
        """Close the board at once, so sub-agents still running stop at their next call."""
        with self._lock:
            if run.status not in (Status.COMPLETE, Status.ABORT):
                run.stop_reason = run.stop_reason or _stop_reason(e)
                run.abort()

    @staticmethod
    def _record_verify_failed(run: Run) -> None:
        last = run.last_verify or {}
        run._record("verify_failed", {"misses": list(last.get("misses") or []), "world_misses": list(last.get("world_misses") or [])})

    def _team_review(self, run: Run, error: BaseException | None) -> None:
        """At the end of a run that had a failure: the kernel's blameless review, on the run and last
        on its record, and its lessons in the shared guidelines. A review never changes the outcome."""
        try:
            review = team_review(run, error)
            if review is None or run.review is not None:
                return
            with self._lock:
                run.review = review
                run._record("team_review", {"what_failed": review["what_failed"], "lessons": review["lessons"]})
            if self.lessons:
                for lesson in review["lessons"]:
                    self.store.add_lesson(lesson)
        except Exception as e:  # never mask the run's own outcome
            try:
                run._record("team_review_failed", {"error": type(e).__name__})
            except Exception:
                pass

    def _admit(self, run: Run) -> None:
        """Before a call. Near a cap, wait for calls in flight and decide on what they really cost.

        Call with the lock held. Far from every cap, calls start at once and run in parallel.
        """
        while True:
            run.assert_running()
            b, n = run.budget, self._inflight.get(id(run), 0)
            if b is None or n == 0:
                return
            calls, tokens = run.usage()
            if calls + n < b.max_calls and tokens + n * b.max_tokens_per_call < b.max_tokens:
                return
            self._settled.wait(timeout=1.0)

    def propose(self, run: Run):
        """Ask the policy head. The kernel does not write the roster here."""
        from .policy import StubPolicy, apply_decision, clamp, encode_board

        policy = self.policy or StubPolicy()
        raw = policy.act(encode_board(run))
        decision = clamp(raw, getattr(policy, "threshold", 0.35))
        result = apply_decision(run, decision)
        return decision, result

    def _arm(self, run: Run) -> None:
        """A run gets its own copy of the engine's budget, with its own clock, so a reused engine
        never hands one run's elapsed time to the next."""
        if run.budget is None:
            run.attach_budget(replace(self.budget, started_at=time.time()))

    def handoff_peer(self, src: Run, dst: Run, claim: str) -> None:
        src.send_peer(src.state.lead_id, claim, peer_id=dst.id)
        dst.receive_peer(src.id, claim)

    def _brief(self, run: Run, function: str, extra: str = "", slot: Slot | None = None, context: str | None = None, mode: str = "") -> Brief:
        """context overrides the live context. Workers get the context as it stood at the
        split, so a sibling's update never reaches their brief."""
        slot = slot or next(s for s in run.state.slots if s.function == function)
        keep = None
        view = ""
        if function == "verifier":
            crit = "; ".join(run.state.success_criteria)
            view = self.verify_view
            independent = view == "independent"
            # The product under review, named as such: a model reads a section called BRIEF as its brief.
            head = "PRODUCT UNDER REVIEW (the lead's current product)" if independent else (
                "PRODUCT UNDER REVIEW (the lead's current product, the same as WORKING product)")
            extra = (f"{head}\n{extra}\n" if extra else "") + (
                "VERIFIER RULE: claim MUST start with PASS or FAIL. "
                "PASS only if the product itself meets every success criterion. "
                "Your own evidence does not count toward a criterion. "
                f"Criteria: {crit}. Do not use the context as the claim."
            )
            if independent:
                # Not the author's notes: the context as the operator gave it, and none of working memory's
                # product or sub-agent reports. The product reaches it once, under PRODUCT UNDER REVIEW.
                keep = checks.INDEPENDENT_FACTS
                if context is None:
                    given = self.store.working_facts(run.id).get("context")
                    context = given if isinstance(given, str) and given else run.state.context
        packet = self.store.scoped_brief(run.id, extra, channel_id=slot.channel_id, keep=keep)
        return Brief(
            slot_function=slot.function,
            skill=slot.skill,
            packet=packet,
            goal=run.state.goal,
            purpose=run.state.purpose,
            context=run.state.context if context is None else context,
            done_when=run.state.done_when,
            channel_id=slot.channel_id or "",
            isolated=True,
            tools=list(slot.tools),
            success_criteria=list(run.state.success_criteria),
            mode=mode,
            view=view,
        )

    def _call(self, run: Run, brief: Brief, slot: Slot | None = None) -> Artifact:
        """One budgeted model call. A malformed reply is asked again once: models slip on the format now
        and then, and one retry is cheaper than losing the run or the part. The retry is a second budgeted
        call, and the failed first one stays on the record."""
        try:
            return self._attempt(run, brief, slot)
        except InvariantError as e:
            if e.code != "SCHEMA" or run.status != Status.ACTIVE:
                raise
            with self._lock:
                run._record("retry", {"slot": slot.id if slot else brief.slot_function,
                                      "channel": brief.channel_id or brief.slot_function, "after": e.code})
            return self._attempt(run, replace(brief, packet=brief.packet + RETRY_NOTE), slot)

    def _reply_room(self, run: Run) -> int:
        """Room a reply needs in the call: the largest reply in this run so far, and at least what the
        adapter expects before it has replied at all."""
        seen = max((c.get("completion_tokens") or 0 for c in run.calls if not c.get("failed")), default=0)
        return max(seen, getattr(self.adapter, "min_reply_tokens", 0))

    def _attempt(self, run: Run, brief: Brief, slot: Slot | None = None) -> Artifact:
        """One budgeted model call. The model runs outside the lock; the board inside it."""
        size = self.adapter.estimate_tokens(brief)
        with self._lock:
            self._arm(run)
            self._admit(run)
            b = run.budget
            reply = self._reply_room(run) if b else 0
            if b and size + reply > b.max_tokens_per_call:
                # Checked before the call, reply included: an oversized call is never sent, so never paid for.
                run.halt(f"brief of ~{size} tokens, plus ~{reply} for the reply, exceeds max_tokens_per_call "
                         f"{b.max_tokens_per_call}; not sent")
            if b:
                # The reply may run only to the cap: an adapter that can asks the endpoint to stop it there.
                brief = replace(brief, max_reply_tokens=max(1, b.max_tokens_per_call - size))
            heard = _sibling_heard(run, brief)
            self._inflight[id(run)] = self._inflight.get(id(run), 0) + 1
        try:
            return self._call_and_record(run, brief, slot, size, heard)
        finally:
            with self._lock:
                left = self._inflight.get(id(run), 1) - 1
                if left:
                    self._inflight[id(run)] = left
                else:
                    self._inflight.pop(id(run), None)
                self._settled.notify_all()

    def _call_record(self, brief: Brief, slot: Slot | None, heard: list[str], latency: float,
                     prompt: int, completion: int, usage_real: bool) -> dict:
        return {
            "slot": (slot.id if slot else brief.slot_function),
            "function": brief.slot_function,
            "channel": brief.channel_id or brief.slot_function,
            "mode": brief.mode,
            "latency_s": round(latency, 4),
            "prompt_tokens": int(prompt),
            "completion_tokens": int(completion),
            "packet": brief.packet,
            "heard_channels": heard,
            "adapter": getattr(self.adapter, "name", ""),
            "tokens_estimated": not usage_real,
            **({"view": brief.view} if brief.view else {}),
        }

    def _call_and_record(self, run: Run, brief: Brief, slot: Slot | None, size: int, heard: list[str]) -> Artifact:
        started = time.perf_counter()
        try:
            art = self.adapter.act(brief)
        except BaseException as e:
            # The request went out and may have been billed: it stays on the record, marked failed,
            # so the budget and every cost report count it.
            usage = getattr(self.adapter, "last_usage", None) or {}
            reported_prompt, reported_completion = _reported(usage.get("prompt_tokens")), _reported(usage.get("completion_tokens"))
            call = self._call_record(brief, slot, heard, time.perf_counter() - started, reported_prompt or size,
                                     reported_completion or 0,
                                     bool(reported_prompt or reported_completion) and not usage.get("estimated"))
            call["failed"] = e.code if isinstance(e, InvariantError) else type(e).__name__
            with self._lock:
                run.adapter_name = getattr(self.adapter, "name", "") or run.adapter_name
                run.record_call(call)
            raise
        latency = time.perf_counter() - started
        usage = getattr(self.adapter, "last_usage", None) or {}
        reported_prompt, reported_completion = _reported(usage.get("prompt_tokens")), _reported(usage.get("completion_tokens"))
        prompt = reported_prompt or size
        completion = reported_completion or _reply_estimate(art)
        # An adapter may fill in its own estimate when the endpoint reports nothing, and says so.
        usage_real = bool(reported_prompt or reported_completion) and not usage.get("estimated")
        # The kernel names the channel, not the model.
        if brief.slot_function == "lead":
            art.channel_id = "lead-plan" if brief.mode == "plan" else "lead-merge"
        elif brief.slot_function == "verifier":
            art.channel_id = "verify"
        elif brief.channel_id:
            art.channel_id = brief.channel_id
        with self._lock:
            run.adapter_name = getattr(self.adapter, "name", "") or run.adapter_name
            run.record_call(self._call_record(brief, slot, heard, latency, prompt, completion, usage_real))
            # Only known tool names. Schema words like "purpose" are not tools.
            toolish = [_tool_name(r) for r in art.requests if _tool_name(r) in TOOL_NAMES]
            if toolish:
                slot_id = slot.id if slot else run.state.lead_id
                try:
                    run.assert_tools(slot_id, toolish)
                except InvariantError as e:
                    run.halt(e.message, code=e.code)
            b = run.budget
            used = int(prompt) + int(completion)
            if b and used > b.max_tokens_per_call:
                run.halt(f"max_tokens_per_call {b.max_tokens_per_call} exceeded ({used})")
            run.assert_within_budget()
        return art

    def _act(self, run: Run, brief: Brief, slot: Slot | None = None, *, reserve: int | None = None,
             toolbox: Toolbox | None = None) -> Artifact:
        """A call plus tool rounds. Allowed tools run, results come back in the next brief.

        reserve: calls that must be left afterwards (the verifier's), so tool rounds stop in time.
        toolbox: a sub-agent's own, open only at its share of the workspace.
        """
        toolbox = toolbox or self.toolbox
        rounds = self.max_tool_rounds
        if reserve is not None and run.budget:
            rounds = max(0, min(rounds, self._calls_left(run) - 1 - reserve))
        art = self._call(run, brief, slot)
        have: set = set()  # files this call holds in full, so no round copies one twice
        for _ in range(rounds):
            wanted = list(dict.fromkeys(r for r in art.requests if _tool_name(r) in RUNNABLE))
            if not wanted:
                return art
            # Reads first, so a search in the same round can leave out what a read already returned.
            wanted.sort(key=lambda r: _tool_name(r) != "read")
            results = []
            if len(wanted) > MAX_TOOL_REQUESTS:
                results.append(f"[{len(wanted) - MAX_TOOL_REQUESTS} more tool requests not run: at most {MAX_TOOL_REQUESTS} per round]")
                wanted = wanted[:MAX_TOOL_REQUESTS]
            for req in wanted:
                with self._lock:
                    run.assert_running()
                out = toolbox.run(req, have)
                results.append(out)
                with self._lock:
                    run._record("tool", {
                        "slot": slot.id if slot else brief.slot_function,
                        "channel": brief.channel_id,
                        "request": str(req)[:200],
                        "chars": len(out),
                        # The files it showed, so a check later knows what the run saw and what it never did.
                        **checks.files_in_result(out),
                    })
            brief = self._current(run, replace(brief, packet=f"{brief.packet}\n{TOOL_RESULTS}\n" + "\n\n".join(results)), slot)
            art = self._call(run, brief, slot)
        if any(_tool_name(r) in RUNNABLE for r in art.requests):
            with self._lock:
                run._record("tool_rounds_exhausted", {"slot": slot.id if slot else brief.slot_function})
        return art

    def _current(self, run: Run, brief: Brief, slot: Slot | None) -> Brief:
        """Kept current (part 8): a member's next call carries the situation as it stands now, as the record
        has it, and says what changed since its last call. Its context and working facts stay as they were."""
        now = {"goal": run.state.goal, "purpose": run.state.purpose, "done_when": run.state.done_when,
               "success_criteria": list(run.state.success_criteria)}
        changed = [k for k, v in now.items() if getattr(brief, k) != v]
        if not changed:
            return brief
        with self._lock:
            run._record("situation_update", {"slot": slot.id if slot else brief.slot_function, "changed": changed})
        return replace(brief, **now, packet=brief.packet + "\n" + SITUATION_CHANGED.format(fields=", ".join(changed)))

    def _decision_point(self, run: Run, at: str, calls: int) -> None:
        """Part 8. Forecast what the rest of the run needs, check the abort criteria, and record both.
        A criterion that is met stops the run here, before it spends the rest of its budget.

        calls: the fewest calls the rest of the loop makes from here."""
        if at not in run.state.checkpoints:
            return
        with self._lock:
            criteria = situation.parse_abort(run.state.abort_criteria)
            fc = situation.forecast(run, at, calls)
            hit = situation.met(run, fc, criteria)
            run.state.projections.append(fc.line())
            run._record("decision_point", fc.as_dict() | {"abort": hit})
            if hit:
                run.halt(f"abort criterion {hit} met at {at}. {fc.line()}", code="ABORT")

    def _reports(self, run: Run, added: list[Slot], arts: list[Artifact | None]) -> tuple[list[str], dict[str, str]]:
        """After the sub-agents report: the parts that failed and the parts handed back, then the reports
        decision point. Each part handed back has a replan request open; the kernel closes it for the lead
        with the method that follows, in which the lead covers the part (INV-14)."""
        reported = {e.detail["channel"]: e.detail["reason"] for e in run.log if e.event == "part_reported"}
        failed = [w.channel_id or "" for w, a in zip(added, arts) if a is None and w.channel_id not in reported]
        self._decision_point(run, "reports", 2)  # the merge and the check
        lead = run.state.lead_id
        for ch in reported:
            run.answer_review(lead, f"replan-{ch}", "CHANGE_METHOD",
                              f"{run.state.method}; the lead covers {ch}, which its sub-agent reported could not be done as planned")
        return failed, reported

    # --- task organization ---

    def _worker_cost(self, subtask: Subtask) -> int:
        """Calls one sub-agent may spend: one, plus tool rounds if its skill has tools."""
        runnable = any(t in RUNNABLE for t in SKILL_TOOLS.get(subtask.skill, ()))
        return 1 + (self.max_tool_rounds if runnable else 0)

    def _merge_cost(self) -> int:
        """Calls the merge may spend: one, plus tool rounds when it may have to read for a left-over part."""
        return 1 + (self.max_tool_rounds if (self.toolbox.roots or self.toolbox.files) else 0)

    def _model_tokens(self, n: int) -> int:
        """n tokens at four characters a token, in the model's own count: the room per call is measured from
        what the model reports, so what the kernel measures in characters must count the same way."""
        ratio = getattr(self.adapter, "token_ratio", 1.0)
        return n if ratio == 1.0 else math.ceil(n * ratio)

    def _material(self, subtask: Subtask) -> dict[str, int] | None:
        """The sub-task's files, in the model's tokens."""
        found = self.toolbox.material(subtask.channel_id, subtask.named_failure)
        return {path: self._model_tokens(tokens) for path, tokens in found.items()} if found else found

    def _overhead(self, run: Run) -> int | None:
        """What one call costs before any material: the lead's latest brief, plus its reply or the room
        the size check keeps for a reply, whichever is larger. The gate and the size check then agree on
        what fits: the gate never keeps work in one call that the size check would refuse to send.

        A planning brief carries more instructions than a working brief, so this
        errs toward splitting, never toward overflowing.
        """
        for c in reversed(run.calls):
            if c.get("function") == "lead":
                return int(c.get("prompt_tokens") or 0) + max(int(c.get("completion_tokens") or 0), self._reply_room(run))
        return None

    def _assess(self, run: Run, subtasks: list[Subtask], *, declared: bool = False) -> list[Assessment]:
        """declared: the operator named these sub-tasks, so the need is theirs to state."""
        b = run.budget
        main = run.state.primary
        if main:
            # The main effort (part 8) is judged first, so it is staffed first when the budget or the cap runs short.
            first = next((s for s in subtasks if s.channel_id == main), None)
            if first is not None:
                subtasks = [first] + [s for s in subtasks if s is not first]
            run._record("main_effort", {"channel": main, "proposed": first is not None})
        if len(subtasks) > MAX_PROPOSALS:
            run._record("gate_overflow", {"proposed": len(subtasks), "considered": MAX_PROPOSALS})
            subtasks = subtasks[:MAX_PROPOSALS]
        verdicts = assess(
            subtasks,
            world=getattr(run, "world", None),
            occupied_channels=[s.channel_id for s in run.state.slots if s.channel_id],
            allow_split=getattr(b, "allow_split", True),
            tier=getattr(b, "tier", ""),
            calls_left=(b.max_calls - len(run.calls)) if b else None,
            # Merge, which reads when it covers a part no sub-agent took, then verify.
            calls_after_split=self._merge_cost() + 1,
            worker_slots_left=MAX_WORKERS - run.state.worker_count(),
            worker_cost=self._worker_cost,
            policy=self.split_policy,
            declared=declared or self.isolation_required,
            material=self._material,
            context_limit=b.max_tokens_per_call if b else None,
            fit_fraction=self.fit_fraction,
            overhead=self._overhead(run),
        )
        for v in verdicts:
            run._record("gate", v.as_dict())
        return verdicts

    def _staff(self, run: Run, legal: list[Assessment]) -> list[Slot]:
        lead = run.state.lead_id
        added = []
        for a in legal:
            worker = Slot(id=f"w-{a.subtask.channel_id}", function="worker", skill=a.subtask.skill, channel_id=a.subtask.channel_id)
            run.set_roster(lead, run.state.slots + [worker], gates=a.gates)
            added.append(worker)
        return added

    def _run_workers(self, run: Run, added: list[Slot], split_context: str, notes: dict[str, str] | None = None) -> list[Artifact | None]:
        """Sub-agents work at the same time, each blind to its siblings, then report in sub-task order.

        notes carries the lead's text from each sub-task to its sub-agent, so a sub-agent
        knows its part and not only its channel name. A sub-agent that failed in a way the team
        absorbs (PART_FAILURES) reports None, and its part is the lead's to cover.
        """

        def one(worker: Slot) -> Artifact:
            note = (notes or {}).get(worker.channel_id or "", "")
            # The files the gates measured for this part. The sub-agent's tools open only these, so it
            # cannot take on its siblings' material and overrun the call the split was sized for.
            files = self.toolbox.material(worker.channel_id or "", note) or {}
            own = sorted(self.toolbox._shown(Path(p)) for p in files)
            brief = self._brief(
                run, "worker",
                extra=f"channel={worker.channel_id} only. Do not see sibling channels."
                + (f" Your files: {', '.join(own)}; your tools open only these. Report what they hold for the goal;"
                   " the other parts are other sub-agents', and the lead combines them." if own else "")
                + (f" Lead's note for this sub-agent: {note}" if note else "")
                + (REPORT_UP_NOTE if self.report_up else ""),
                slot=worker, context=split_context, mode="work",
            )
            try:
                return self._act(run, brief, slot=worker, toolbox=self.toolbox.scoped(files) if files else None)
            except InvariantError as e:
                if e.code in PART_FAILURES and run.status == Status.ACTIVE:
                    # The part is not lost: it goes back to the lead, and the siblings carry on.
                    return e
                self._abort(run, e)
                raise
            except BaseException as e:
                self._abort(run, e)
                raise

        if self.parallel and len(added) > 1:
            with ThreadPoolExecutor(max_workers=len(added)) as pool:
                futures = [pool.submit(one, w) for w in added]
                try:
                    errors = [f.exception() for f in futures]
                except BaseException as e:
                    # Before the pool joins its threads: Ctrl-C lands here, and siblings must stop now.
                    self._abort(run, e)
                    raise
            errors = [e for e in errors if e is not None]
            if errors:
                # Raise the cause. A sibling that found the board closed only reports the consequence.
                raise next((e for e in errors if _stop_reason(e) == run.stop_reason), errors[0])
            arts = [f.result() for f in futures]
        else:
            arts = [one(w) for w in added]
        # Accepted in sub-task order, failures too, so the record does not depend on timing.
        for i, (worker, art) in enumerate(zip(added, arts)):
            if isinstance(art, InvariantError):  # failed; the lead covers this part
                run._record("part_failed", {"channel": worker.channel_id, "slot": worker.id,
                                            "code": art.code, "error": str(art)[:200]})
                arts[i] = None
                continue
            why = _plan_wrong(art) if self.report_up else None
            if why is not None:
                # Reported up (part 8): the plan is wrong for this part. It goes back to the lead with the
                # reason, as a failed part does, and a replan request stays open until the method changes.
                run._record("part_reported", {"channel": worker.channel_id, "slot": worker.id, "reason": why})
                run.request_replan(f"{worker.channel_id}: {why}", note_id=f"replan-{worker.channel_id}")
                arts[i] = None
                continue
            run.accept_artifact(art)
            run.post_delta(Delta(claim=art.context_update or art.claim, evidence=list(art.evidence), uncertainty=art.uncertainty, channel_id=art.channel_id, stream="merge"))
            self.store.remember_working(run.id, f"channel:{worker.channel_id}", art.claim)
        return arts

    def _cover(self, run: Run, verdicts: list[Assessment], failed: list[str], reported: dict[str, str] | None = None) -> str:
        """Parts the lead covers in the merge: refused for capacity or a malformed proposal, or whose
        sub-agent failed or handed it back. Gives the lead a skill that can read, and returns the brief
        text naming them."""
        refused = [v.subtask.channel_id for v in verdicts if v.gate in ("should_we", "could_we")]
        # Proposals past the cap were never judged, so they have no verdict; their parts are the lead's too.
        past = next((e.detail for e in reversed(run.log) if e.event == "gate_overflow"), None)
        unjudged = past["proposed"] - past["considered"] if past else 0
        if not refused and not failed and not unjudged and not reported:
            return ""
        lead = run.state.lead_id
        run.switch_skill(lead, lead, self._single_agent_skill([]), "merge and cover parts no sub-agent finished")
        text = ""
        if refused:
            text += f" These parts got no sub-agent and are yours to cover: {', '.join(refused)}."
        if failed:
            text += f" These parts' sub-agents failed, so they are yours to cover: {', '.join(failed)}."
        if reported:
            text += (" These parts' sub-agents reported they could not be done as planned, so they are yours to cover: "
                     + "; ".join(f"{ch} (its reason: {why})" for ch, why in reported.items()) + ".")
        if unjudged:
            text += f" {unjudged} more proposed part(s) came past the cap of {MAX_PROPOSALS} and are yours to cover too."
        return text

    def _calls_left(self, run: Run) -> int:
        b = run.budget
        return (b.max_calls - len(run.calls)) if b else 1 << 30

    def _verifier_brief(self, run: Run, product: Artifact) -> Brief:
        """The verifier's brief: the product, in the engine's view, with the sources the kernel opened.

        Sources go in as many as fit the per-call limit, in the order checks.pick ranks them, and the
        brief says how many did not. What was opened, and why, goes on the record."""
        extra = _for_review(product)
        if self.verify_sources == "none":
            return self._brief(run, "verifier", extra=extra, mode="verify")
        names = self.toolbox.shown_files()
        picks = checks.pick(run, product, names, self.verify_sources, sample=self.verify_sample)
        flagged = checks.misquoted(self.toolbox, product, names)
        if flagged:
            extra += "\nKERNEL CHECK: these evidence quotes are not in the files they cite:\n" + "\n".join(f"- {f}" for f in flagged)
        blocks = [checks.source_block(self.toolbox, name, why) for name, why in picks]
        b = run.budget
        limit = b.max_tokens_per_call - self._reply_room(run) if b else None
        def with_sources(kept: list[str]) -> str:
            more = len(blocks) - len(kept)
            note = f"\n[{more} more source(s) not shown: over the per-call limit]" if more else ""
            return extra + f"\n{checks.SOURCES_HEAD}\n" + "\n\n".join(kept) + note + f"\n{checks.SOURCE_RULE}"

        shown: list[str] = []
        for block in blocks:
            body = with_sources(shown + [block])
            if limit is not None and self.adapter.estimate_tokens(self._brief(run, "verifier", extra=body, mode="verify")) > limit:
                break
            shown.append(block)
        if shown:
            extra = with_sources(shown)
        with self._lock:
            run._record("verify_sources", {
                "view": self.verify_view, "sources": self.verify_sources,
                "picked": [{"file": name, "why": why} for name, why in picks],
                "shown": len(shown), "misquoted": len(flagged),
            })
        return self._brief(run, "verifier", extra=extra, mode="verify")

    def _verify(self, run: Run, product: Artifact, *, adapt: bool) -> tuple[Artifact, bool]:
        """Check the product. On a failed check, change the method once if the tier and budget allow."""
        lead = run.state.lead_id
        check = self._act(run, self._verifier_brief(run, product))
        verified = _verifier_accepts(check, run, product)
        run.accept_artifact(check)
        if not verified:
            self._record_verify_failed(run)
        b = run.budget
        rework = not verified and adapt and getattr(b, "allow_adapt", True)
        self._decision_point(run, "verdict", 2 if rework else 0)  # a rework and its check, or nothing
        if rework and self._calls_left(run) >= 2:
            last = run.last_verify or {}
            misses = list(last.get("misses", [])) + list(last.get("world_misses", []))
            run.request_replan(f"verifier did not pass: {check.claim[:160]}; misses: {', '.join(misses) or 'none named'}")
            run.answer_review(lead, "replan", "CHANGE_METHOD", f"rework the product to meet: {'; '.join(run.state.success_criteria)}")
            product = self._act(run, self._brief(
                run, "lead",
                extra=(
                    "REWORK. The verifier failed the last product. "
                    f"Misses: {', '.join(misses) or 'none named'}. Last product: {product.claim[:400]}"
                ),
                mode="rework",
            ), reserve=1)
            run.accept_artifact(product)
            # The reworked product replaces the last one everywhere the verifier looks.
            self.store.remember_working(run.id, "product", product.claim)
            check = self._act(run, self._verifier_brief(run, product))
            verified = _verifier_accepts(check, run, product)
            run.accept_artifact(check)
            if not verified:
                self._record_verify_failed(run)
        if not verified:
            run.mark_stop_rule_failed("verifier")
            run.halt("verifier did not PASS named success criteria", code="VERIFY")
        return product, verified

    def _propose(self, run: Run) -> list[Subtask]:
        """The lead reads the context and proposes sub-tasks. Strategies override this."""
        lead = run.state.lead_id
        run.switch_skill(lead, lead, "reason", "read the context; propose sub-tasks only for independent work")
        base = PLAN_BRIEF.format(skills="|".join(SKILLS))
        extra = base + self._size_note(run, base)
        plan = self._act(run, self._brief(run, "lead", extra=extra, mode="plan"))
        run.accept_artifact(plan)
        return parse_proposals(plan.requests)

    def _size_note(self, run: Run, plan: str) -> str:
        """What the gates will measure, told to the lead before it plans: what one call holds and how big the
        workspace files are. Not told, a lead on a tight cap proposed nothing and the work overflowed."""
        b = run.budget
        sizes = [self._model_tokens(n) for n in self.toolbox.file_sizes()] if b and b.max_tokens_per_call else []
        if not sizes:
            return ""
        brief = self.adapter.estimate_tokens(self._brief(run, "lead", extra=plan, mode="plan"))
        return (f" SIZE. One call holds at most {b.max_tokens_per_call:,} tokens in all: its brief, the files it reads "
                f"and its reply. A brief like this one takes about {brief:,}, and a reply can take as much again. "
                f"The workspace has {len(sizes)} file(s) of about {min(sizes):,} to {max(sizes):,} tokens each.")

    def _judge(self, run: Run, subtasks: list[Subtask]) -> list[Assessment]:
        """The gates. Strategies override this."""
        return self._assess(run, subtasks)

    def _single_agent_skill(self, verdicts: list[Assessment]) -> str:
        """A single agent switches to the skill the work needs; with a workspace, that includes reading it."""
        single = next((v for v in verdicts if v.refused == LEAD_COVERS), None)
        workspace = bool(self.toolbox.roots or self.toolbox.files)
        skill = single.subtask.skill if single else ("retrieve" if workspace else "draft")
        if workspace and not any(t in RUNNABLE for t in SKILL_TOOLS.get(skill, ())):
            skill = "retrieve"
        return skill

    @staticmethod
    def _account(verdicts: list[Assessment], added: list[Slot], failed: list[str] | None = None,
                 reported: dict[str, str] | None = None) -> str:
        """The lead's answer to the operator, built from the gate record."""
        refused = [f"{v.subtask.channel_id}: {v.refused}" for v in verdicts if not v.legal]
        if failed:
            refused = refused + [f"{c}: its sub-agent failed, and the lead covered the part" for c in failed]
        if reported:
            refused = refused + [f"{c}: its sub-agent reported the plan wrong for it, and the lead covered the part" for c in reported]
        if added:
            answer = f"{len(added)} sub-agents: {', '.join(w.channel_id or '' for w in added)}"
        elif verdicts:
            answer = "single agent"
        else:
            answer = "single agent: the lead proposed no independent parts"
        return answer + (f"; refused {'; '.join(refused)}" if refused else "")

    def _close(self, run: Run, product: Artifact, operator_question: str, response: str, reason: str, out: str) -> str:
        lead = run.state.lead_id
        question = OperatorQuestion(operator_question).admit()
        note = run.open_review(question, "question-1")
        run.answer_review(lead, note.id, response, reason)
        moved = run.review_if_context_changed()
        if moved and getattr(moved.status, "value", moved.status) == "open":
            run.answer_review(lead, moved.id, "KEEP_ROSTER", "purpose holds after the context changed")
        run.report_out(lead, out)
        fire_auto_cues(run)
        run.complete()
        self.store.archive_episode(run.id, run.summary() | {"product": product.claim})
        return question

    # --- runs ---

    @_aborts_on_error
    def run_task(self, run: Run, *, context: str, operator_question: str = "Could a single agent have done this?", axes: list[str] | None = None) -> LoopResult:
        """The lead reads the situation and organizes the team. The kernel judges it.

        1. Read the context. The lead proposes sub-tasks for independent parts (or none).
        2. Gates judge every proposal. Two or more legal sub-tasks: fan out, run them
           at the same time, merge. Otherwise a single agent; if the one open part needs
           a skill, the lead switches to it.
        3. Verify. If the product fails and the tier allows, request a replan,
           change the method, rework once.
        4. The operator's question is answered from the gate record.
        """
        self._arm(run)
        run.assert_running()
        lead = run.state.lead_id
        run.update_context(lead, context)
        self.store.remember_working(run.id, "context", context)

        verdicts = self._judge(run, self._propose(run))
        legal = [v for v in verdicts if v.legal]
        split = len(legal) >= self.min_split
        # The sub-agents, the merge and the check; or the work and the check.
        self._decision_point(run, "plan", len(legal) + 2 if split else 2)

        added: list[Slot] = []
        failed: list[str] = []
        reported: dict[str, str] = {}
        if split:
            run.set_method(lead, "sub-agents: " + ", ".join(v.subtask.channel_id for v in legal), axes or ["parallel", "fan_in"])
            split_context = run.state.context
            added = self._staff(run, legal)
            arts = self._run_workers(run, added, split_context, notes={v.subtask.channel_id: v.subtask.named_failure for v in legal})
            failed, reported = self._reports(run, added, arts)
            extra = "MERGE. Integrate the sub-agent results against the goal. Do not invent what a sub-agent did not report."
            # Parts refused for capacity or a malformed proposal, and parts whose sub-agent failed or handed
            # them back, still need doing: the lead covers them.
            cover = self._cover(run, verdicts, failed, reported)
            if cover:
                extra += cover
            else:
                run.switch_skill(lead, lead, "reason", "merge sub-agent results")
            product = self._act(run, self._brief(run, "lead", extra=extra, mode="integrate"), reserve=1)
        else:
            skill = self._single_agent_skill(verdicts)
            run.set_method(lead, f"single agent: {skill}", axes or ["sequential"])
            run.switch_skill(lead, lead, skill, "a single agent does the work")
            product = self._act(run, self._brief(run, "lead", extra="WORK. Do the work yourself, as a single agent.", mode="work"), reserve=1)
        run.accept_artifact(product)
        self.store.remember_working(run.id, "product", product.claim)

        product, verified = self._verify(run, product, adapt=True)
        reason = self._account(verdicts, added, failed, reported)
        question = self._close(run, product, operator_question, "KEEP_ROSTER", reason, f"workers={len(added)}; goal={run.state.goal}")
        return LoopResult(
            run=run, product=product, verified=verified, operator_question=question,
            lead_answer="KEEP_ROSTER", split=bool(added), channels=[w.channel_id or "" for w in added],
            verdicts=verdicts,
        )

    @_aborts_on_error
    def run_single(self, run: Run, *, context: str, operator_question: str, lead_response: str = "KEEP_ROSTER", lead_reason: str = "goal still valid; keep the roster") -> LoopResult:
        self._arm(run)
        run.assert_running()
        lead = run.state.lead_id
        run.update_context(lead, context)
        self.store.remember_working(run.id, "context", context)
        run.switch_skill(lead, lead, "draft", "write the default task")
        product = self._act(run, self._brief(run, "lead", extra="write default task", mode="work"))
        run.accept_artifact(product)
        self.store.remember_working(run.id, "product", product.claim)
        product, verified = self._verify(run, product, adapt=False)
        question = self._close(run, product, operator_question, lead_response, lead_reason, f"status={run.status.value}; goal={run.state.goal}")
        return LoopResult(run=run, product=product, verified=verified, operator_question=question, lead_answer=lead_response, split=False, channels=[])

    @_aborts_on_error
    def run_fanout(self, run: Run, *, context: str, subtasks: list[Subtask], axes: list[str], operator_question: str, lead_response: str = "CHANGE_METHOD", lead_reason: str = "the sub-tasks are independent; the method fans out") -> LoopResult:
        """Operator names the subtasks. The same gates judge them as judge the lead's."""
        self._arm(run)
        run.assert_running()
        if run.budget and not getattr(run.budget, "allow_split", True):
            run.halt(f"budget tier {getattr(run.budget, 'tier', '?')} cannot fan out")
        lead = run.state.lead_id
        run.update_context(lead, context)
        self.store.remember_working(run.id, "context", context)
        run.switch_skill(lead, lead, "reason", "choose a method for the context")
        run.set_method(lead, "multi-axis", axes)
        verdicts = self._assess(run, subtasks, declared=True)
        split_context = run.state.context
        legal = [v for v in verdicts if v.legal]
        self._decision_point(run, "plan", len(legal) + 2)  # the sub-agents, the merge and the check
        added = self._staff(run, legal)
        arts = self._run_workers(run, added, split_context, notes={v.subtask.channel_id: v.subtask.named_failure for v in legal})
        failed, reported = self._reports(run, added, arts)
        # Refused for capacity or a malformed spec, or a sub-agent that failed or handed its part back: never silently dropped.
        extra = "integrate isolated artifacts; do not invent subtasks." + self._cover(run, verdicts, failed, reported)
        integrate = self._act(run, self._brief(run, "lead", extra=extra, mode="integrate"), reserve=1)
        run.accept_artifact(integrate)
        integrate, verified = self._verify(run, integrate, adapt=False)
        if added:
            run.send_peer(lead, f"run {run.id} holding {len(added)} channels", peer_id="peer-run")
            if failed:
                lead_reason = f"{lead_reason}; {', '.join(failed)}: the sub-agent failed, and the lead covered the part"
            if reported:
                lead_reason = f"{lead_reason}; {', '.join(reported)}: the sub-agent reported the plan wrong for it, and the lead covered the part"
        else:
            # No sub-agent was staffed: the answer says so, from the gate record, instead of claiming a fan-out.
            lead_response, lead_reason = "KEEP_ROSTER", self._account(verdicts, added)
        question = self._close(run, integrate, operator_question, lead_response, lead_reason, f"split={len(added)}; goal={run.state.goal}")
        return LoopResult(run=run, product=integrate, verified=verified, operator_question=question, lead_answer=lead_response, split=len(added) > 0, channels=[w.channel_id or "" for w in added], verdicts=verdicts)

    @_aborts_on_error
    def run_replan(self, run: Run, *, context: str, replan_reason: str, new_method: str, axes: list[str], operator_question: str = "Confirm the new method serves the goal") -> LoopResult:
        self._arm(run)
        run.assert_running()
        if run.budget and not getattr(run.budget, "allow_adapt", True):
            run.halt(f"budget tier {getattr(run.budget, 'tier', '?')} cannot replan")
        lead = run.state.lead_id
        run.update_context(lead, context)
        self.store.remember_working(run.id, "context", context)
        run.request_replan(replan_reason)
        run.answer_review(lead, "replan", "CHANGE_METHOD", new_method)
        run.set_method(lead, new_method, axes)
        run.switch_skill(lead, lead, "draft", f"execute {new_method}")
        product = self._act(run, self._brief(run, "lead", extra=f"new method: {new_method}", mode="work"))
        run.accept_artifact(product)
        product, verified = self._verify(run, product, adapt=False)
        question = self._close(run, product, operator_question, "KEEP_ROSTER", "method already changed; keep the new method", f"method={new_method}; goal={run.state.goal}")
        return LoopResult(run=run, product=product, verified=verified, operator_question=question, lead_answer="KEEP_ROSTER", split=False, channels=[])
