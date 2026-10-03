from __future__ import annotations

import functools
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from .adapters import TOOL_RESULTS, Brief, OperatorQuestion, ModelAdapter, StubAdapter
from .budget import Budget
from .cues import fire_auto_cues
from .errors import InvariantError
from .gates import LEAD_COVERS, Assessment, Subtask, assess
from .memory_store import MemoryStore
from .run import Run
from .models import MAX_WORKERS, SKILL_TOOLS, SKILLS, Artifact, Delta, Slot, Status
from .subtasks import parse_subtasks
from .tools import RUNNABLE, Toolbox, parse_request


def score_criteria(product: Artifact | None, criteria: list[str]) -> dict:
    """Criteria must show in the product. The Verifier cannot vouch for them by echo."""
    parts = []
    if product:
        parts.extend([product.claim, *product.evidence, product.context_update])
    blob = " ".join(parts).lower()
    hits, misses = [], []
    for raw in criteria:
        token = raw.strip().lower()
        if token and token in blob:
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
        if not merged:
            misses.append("world: workers exist but merged no results")
    if run.open_review_ids():
        misses.append("world: a review is still open")
    return misses


def _verifier_accepts(check: Artifact, run: Run, product: Artifact | None = None) -> bool:
    upper = check.claim.strip().upper()
    if not upper.startswith("PASS") or "FAIL" in upper:
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

PLAN_BRIEF = (
    "PLAN. Decide how to staff this task. Default is a single agent: you do the work yourself. "
    "Propose a sub-agent only for a part of the work that is independent of the rest "
    "and should not share a context with it. For each, add a request "
    "'subtask:<channel>@<skill>=<named_failure>' where skill is one of {skills} and named_failure "
    "says what goes wrong if a single agent does it (underscores for spaces). "
    "A sub-agent that must search or read the workspace needs skill retrieve (or observe to list files). "
    "Propose nothing if a single agent is enough. The kernel judges the proposal; you do not change the roster. "
    "claim: your read of the situation in one or two sentences."
)


def _tool_name(request: str) -> str:
    return parse_request(request)[0]


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


def _first_per_channel(subtasks: list[Subtask]) -> list[Subtask]:
    seen, out = set(), []
    for s in subtasks:
        if s.channel_id not in seen:
            seen.add(s.channel_id)
            out.append(s)
    return out


def _aborts_on_error(method):
    """A run that dies on an invariant leaves the board ABORT, not ACTIVE."""

    @functools.wraps(method)
    def wrapper(self, run: Run, *args, **kwargs):
        try:
            return method(self, run, *args, **kwargs)
        except InvariantError as e:
            if run.status == Status.ACTIVE:
                run.stop_reason = run.stop_reason or str(e)
                run.abort()
            raise

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
    ):
        self.store = store
        self.adapter = adapter or StubAdapter()
        self.budget = budget or Budget()
        self.policy = policy
        self.toolbox = toolbox or Toolbox()
        self.parallel = parallel
        self.max_tool_rounds = max_tool_rounds
        # Sub-agents run in threads; every run mutation in a call goes through this.
        self._lock = threading.RLock()

    def propose(self, run: Run):
        """Ask the policy head. The kernel does not write the roster here."""
        from .policy import StubPolicy, apply_decision, clamp, encode_board

        policy = self.policy or StubPolicy()
        raw = policy.act(encode_board(run))
        decision = clamp(raw, getattr(policy, "threshold", 0.35))
        result = apply_decision(run, decision)
        return decision, result

    def _arm(self, run: Run) -> None:
        if run.budget is None:
            run.attach_budget(self.budget)

    def handoff_peer(self, src: Run, dst: Run, claim: str) -> None:
        src.send_peer(src.state.lead_id, claim, peer_id=dst.id)
        dst.receive_peer(src.id, claim)

    def _brief(self, run: Run, function: str, extra: str = "", slot: Slot | None = None, context: str | None = None, mode: str = "") -> Brief:
        """context overrides the live context. Workers get the context as it stood at the
        split, so a sibling's update never reaches their brief."""
        slot = slot or next(s for s in run.state.slots if s.function == function)
        if function == "verifier":
            crit = "; ".join(run.state.success_criteria)
            extra = (
                (extra + "\n") if extra else ""
            ) + (
                "VERIFIER RULE: claim MUST start with PASS or FAIL. "
                "PASS only if the product itself meets every success criterion. "
                "Your own evidence does not count toward a criterion. "
                f"Criteria: {crit}. Do not use the context as the claim."
            )
        packet = self.store.scoped_brief(run.id, extra, channel_id=slot.channel_id)
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
        )

    def _call(self, run: Run, brief: Brief, slot: Slot | None = None) -> Artifact:
        """One budgeted model call. The model runs outside the lock; the board inside it."""
        with self._lock:
            self._arm(run)
            run.assert_running()
            heard = _sibling_heard(run, brief)
        started = time.perf_counter()
        art = self.adapter.act(brief)
        latency = time.perf_counter() - started
        usage = getattr(self.adapter, "last_usage", None) or {}
        prompt = usage.get("prompt_tokens") or max(1, len(brief.packet + brief.goal + brief.purpose + brief.context) // 4)
        completion = usage.get("completion_tokens") or max(1, len(art.claim) // 4)
        usage_real = bool(usage.get("prompt_tokens") or usage.get("completion_tokens"))
        # The kernel names the channel, not the model.
        if brief.slot_function == "lead":
            art.channel_id = "lead-plan" if brief.mode == "plan" else "lead-merge"
        elif brief.slot_function == "verifier":
            art.channel_id = "verify"
        elif brief.channel_id:
            art.channel_id = brief.channel_id
        with self._lock:
            run.adapter_name = getattr(self.adapter, "name", "") or run.adapter_name
            run.record_call({
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
            })
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

    def _act(self, run: Run, brief: Brief, slot: Slot | None = None) -> Artifact:
        """A call plus tool rounds. Allowed tools run, results come back in the next brief."""
        art = self._call(run, brief, slot)
        for _ in range(self.max_tool_rounds):
            wanted = [r for r in art.requests if _tool_name(r) in RUNNABLE]
            if not wanted:
                return art
            results = []
            for req in wanted:
                out = self.toolbox.run(req)
                results.append(out)
                with self._lock:
                    run._record("tool", {
                        "slot": slot.id if slot else brief.slot_function,
                        "channel": brief.channel_id,
                        "request": str(req)[:200],
                        "chars": len(out),
                    })
            brief = replace(brief, packet=f"{brief.packet}\n{TOOL_RESULTS}\n" + "\n\n".join(results))
            art = self._call(run, brief, slot)
        if any(_tool_name(r) in RUNNABLE for r in art.requests):
            with self._lock:
                run._record("tool_rounds_exhausted", {"slot": slot.id if slot else brief.slot_function})
        return art

    # --- task organization ---

    def _worker_cost(self, subtask: Subtask) -> int:
        """Calls one sub-agent may spend: one, plus tool rounds if its skill has tools."""
        runnable = any(t in RUNNABLE for t in SKILL_TOOLS.get(subtask.skill, ()))
        return 1 + (self.max_tool_rounds if runnable else 0)

    def _assess(self, run: Run, subtasks: list[Subtask]) -> list[Assessment]:
        b = run.budget
        verdicts = assess(
            _first_per_channel(subtasks),
            world=getattr(run, "world", None),
            occupied_channels=[s.channel_id for s in run.state.slots if s.channel_id],
            allow_split=getattr(b, "allow_split", True),
            tier=getattr(b, "tier", ""),
            calls_left=(b.max_calls - len(run.calls)) if b else None,
            worker_slots_left=MAX_WORKERS - run.state.worker_count(),
            worker_cost=self._worker_cost,
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

    def _run_workers(self, run: Run, added: list[Slot], split_context: str, notes: dict[str, str] | None = None) -> list[Artifact]:
        """Sub-agents work at the same time, each blind to its siblings, then report in sub-task order.

        notes carries the lead's text from each sub-task to its sub-agent, so a sub-agent
        knows its part and not only its channel name.
        """

        def one(worker: Slot) -> Artifact:
            note = (notes or {}).get(worker.channel_id or "", "")
            brief = self._brief(
                run, "worker",
                extra=f"channel={worker.channel_id} only. Do not see sibling channels."
                + (f" Lead's note for this sub-agent: {note}" if note else ""),
                slot=worker, context=split_context, mode="work",
            )
            return self._act(run, brief, slot=worker)

        if self.parallel and len(added) > 1:
            with ThreadPoolExecutor(max_workers=len(added)) as pool:
                futures = [pool.submit(one, w) for w in added]
                arts = [f.result() for f in futures]
        else:
            arts = [one(w) for w in added]
        for worker, art in zip(added, arts):
            run.accept_artifact(art)
            run.post_delta(Delta(claim=art.context_update or art.claim, evidence=list(art.evidence), uncertainty=art.uncertainty, channel_id=art.channel_id, stream="merge"))
            self.store.remember_working(run.id, f"channel:{worker.channel_id}", art.claim)
        return arts

    def _calls_left(self, run: Run) -> int:
        b = run.budget
        return (b.max_calls - len(run.calls)) if b else 1 << 30

    def _verify(self, run: Run, product: Artifact, *, adapt: bool) -> tuple[Artifact, bool]:
        """Check the product. On a failed check, change the method once if the tier and budget allow."""
        lead = run.state.lead_id
        check = self._act(run, self._brief(run, "verifier", extra=product.claim, mode="verify"))
        verified = _verifier_accepts(check, run, product)
        run.accept_artifact(check)
        b = run.budget
        if not verified and adapt and getattr(b, "allow_adapt", True) and self._calls_left(run) >= 2:
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
            ))
            run.accept_artifact(product)
            check = self._act(run, self._brief(run, "verifier", extra=product.claim, mode="verify"))
            verified = _verifier_accepts(check, run, product)
            run.accept_artifact(check)
        if not verified:
            run.mark_stop_rule_failed("verifier")
            run.halt("verifier did not PASS named success criteria")
        return product, verified

    def _propose(self, run: Run) -> list[Subtask]:
        """The lead reads the context and proposes sub-tasks. Strategies override this."""
        lead = run.state.lead_id
        run.switch_skill(lead, lead, "reason", "read the context; propose sub-tasks only for independent work")
        plan = self._act(run, self._brief(run, "lead", extra=PLAN_BRIEF.format(skills="|".join(SKILLS)), mode="plan"))
        run.accept_artifact(plan)
        return parse_subtasks(" ".join(plan.requests))

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
    def _account(verdicts: list[Assessment], added: list[Slot]) -> str:
        """The lead's answer to the operator, built from the gate record."""
        refused = [f"{v.subtask.channel_id}: {v.refused}" for v in verdicts if not v.legal]
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

        added: list[Slot] = []
        if len(legal) >= self.min_split:
            run.set_method(lead, "sub-agents: " + ", ".join(v.subtask.channel_id for v in legal), axes or ["parallel", "fan_in"])
            split_context = run.state.context
            added = self._staff(run, legal)
            self._run_workers(run, added, split_context, notes={v.subtask.channel_id: v.subtask.named_failure for v in legal})
            # Parts refused for capacity or a malformed proposal still need doing: the lead covers them.
            leftover = [v.subtask.channel_id for v in verdicts if v.gate in ("should_we", "could_we")]
            extra = "MERGE. Integrate the sub-agent results against the goal. Do not invent what a sub-agent did not report."
            if leftover:
                run.switch_skill(lead, lead, self._single_agent_skill([]), "merge and cover parts no sub-agent took")
                extra += f" These parts got no sub-agent and are yours to cover: {', '.join(leftover)}."
            else:
                run.switch_skill(lead, lead, "reason", "merge sub-agent results")
            product = self._act(run, self._brief(run, "lead", extra=extra, mode="integrate"))
        else:
            skill = self._single_agent_skill(verdicts)
            run.set_method(lead, f"single agent: {skill}", axes or ["sequential"])
            run.switch_skill(lead, lead, skill, "a single agent does the work")
            product = self._act(run, self._brief(run, "lead", extra="WORK. Do the work yourself, as a single agent.", mode="work"))
        run.accept_artifact(product)
        self.store.remember_working(run.id, "product", product.claim)

        product, verified = self._verify(run, product, adapt=True)
        reason = self._account(verdicts, added)
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
        verdicts = self._assess(run, subtasks)
        split_context = run.state.context
        legal = [v for v in verdicts if v.legal]
        added = self._staff(run, legal)
        self._run_workers(run, added, split_context, notes={v.subtask.channel_id: v.subtask.named_failure for v in legal})
        integrate = self._act(run, self._brief(run, "lead", extra="integrate isolated artifacts; do not invent subtasks", mode="integrate"))
        run.accept_artifact(integrate)
        integrate, verified = self._verify(run, integrate, adapt=False)
        if added:
            run.send_peer(lead, f"run {run.id} holding {len(added)} channels", peer_id="peer-run")
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
