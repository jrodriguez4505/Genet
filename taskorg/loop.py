from __future__ import annotations

import functools
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from .adapters import TOOL_RESULTS, Brief, EchoWhy, ModelAdapter, StubAdapter
from .budget import Budget
from .cues import fire_auto_cues
from .errors import InvariantError
from .gates import Assessment, Seam, assess
from .memory_store import MemoryStore
from .mission import Mission
from .models import MAX_WORKERS, QUAL_TOOLS, QUALS, Artifact, Delta, Slot, Status
from .seams import parse_seams
from .tools import RUNNABLE, Toolbox, parse_request


def score_criteria(product: Artifact | None, criteria: list[str]) -> dict:
    """Criteria must show in the product. The Verifier cannot vouch for them by echo."""
    parts = []
    if product:
        parts.extend([product.claim, *product.evidence, product.delta_to_picture])
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


def world_misses(mission: Mission, product: Artifact | None) -> list[str]:
    """Verifier looks at state, not only words."""
    misses = []
    if not (mission.picture.current_picture or "").strip():
        misses.append("world: Where is empty")
    if not (mission.picture.method or "").strip():
        misses.append("world: How is empty")
    if product is not None and not (product.claim or "").strip():
        misses.append("world: product claim empty")
    if mission.picture.worker_count() > 0:
        elem = [d for d in mission.deltas if d.net == "element"]
        if not elem:
            misses.append("world: Workers exist but no element deltas")
    if mission.open_why_ids():
        misses.append("world: Why still open")
    return misses


def _verifier_accepts(check: Artifact, mission: Mission, product: Artifact | None = None) -> bool:
    upper = check.claim.strip().upper()
    if not upper.startswith("PASS") or "FAIL" in upper:
        scored = score_criteria(product, mission.picture.success_criteria)
        scored["world_misses"] = ["claim is not PASS"]
        mission.last_verify = scored
        return False
    scored = score_criteria(product, mission.picture.success_criteria)
    w = world_misses(mission, product)
    scored["world_misses"] = w
    mission.last_verify = scored
    return scored["score"] >= 1.0 and not scored["misses"] and not w


@dataclass
class LoopResult:
    mission: Mission
    product: Artifact | None
    verified: bool
    why_question: str | None
    why_response: str | None
    split: bool = False
    channels: list[str] | None = None
    verdicts: list[Assessment] | None = None


# Tool names the kernel recognizes in artifact.requests. Anything else is free text.
TOOL_NAMES = {"write", "verify", "observe", "read", "retrieve", "simulate", "spawn"}

PLAN_BRIEF = (
    "PLAN. Decide the task organization. Default is one body: you do the work yourself. "
    "Propose a separate element only for a part of the work that is independent of the rest "
    "and should not share a context with it. For each, add a request "
    "'seam:<channel>@<qual>=<named_failure>' where qual is one of {quals} and named_failure "
    "says what goes wrong if one body does it (underscores for spaces). "
    "An element that must search or read the workspace needs qual retrieve (or observe to list files). "
    "Propose nothing if one body is enough. The kernel judges the proposal; you do not change the roster. "
    "claim: your read of the situation in one or two sentences."
)


def _tool_name(request: str) -> str:
    return parse_request(request)[0]


def _sibling_heard(mission: Mission, brief: Brief) -> list[str]:
    """Which sibling channels' products are visible anywhere in this worker's brief."""
    if brief.slot_function != "worker" or not brief.channel_id:
        return []
    worker_channels = {s.channel_id for s in mission.picture.slots if s.function == "worker" and s.channel_id}
    seen_text = f"{brief.packet}\n{brief.picture}"
    heard = []
    for other in sorted(worker_channels - {brief.channel_id}):
        marks = [f"channel:{other}"]
        for art in mission.artifacts:
            if art.channel_id == other:
                marks.extend(t for t in (art.claim, art.delta_to_picture) if len(t.strip()) >= 8)
        if any(m in seen_text for m in marks):
            heard.append(other)
    return heard


def _first_per_channel(seams: list[Seam]) -> list[Seam]:
    seen, out = set(), []
    for s in seams:
        if s.channel_id not in seen:
            seen.add(s.channel_id)
            out.append(s)
    return out


def _aborts_on_error(run):
    """A run that dies on an invariant leaves the board ABORT, not ACTIVE."""

    @functools.wraps(run)
    def wrapper(self, mission: Mission, *args, **kwargs):
        try:
            return run(self, mission, *args, **kwargs)
        except InvariantError as e:
            if mission.status == Status.ACTIVE:
                mission.stop_reason = mission.stop_reason or str(e)
                mission.abort()
            raise

    return wrapper


class Engine:
    """Graph owns authority. Adapter only fills artifacts.

    toolbox     sandboxed read-only tools for specialists (none attached by default)
    parallel    elements call the model at the same time; their results are
                accepted in seam order so the board is deterministic
    """

    # A split needs this many legal elements. Below it, one body does the work.
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
        # Elements run in threads; every mission mutation in a call goes through this.
        self._lock = threading.RLock()

    def propose(self, mission: Mission):
        """Ask the policy head. Kernel does not write Who here."""
        from .policy import StubPolicy, apply_decision, clamp, encode_board

        head = self.policy or StubPolicy()
        raw = head.act(encode_board(mission))
        decision = clamp(raw, getattr(head, "threshold", 0.35))
        result = apply_decision(mission, decision)
        return decision, result

    def _arm(self, mission: Mission) -> None:
        if mission.budget is None:
            mission.attach_budget(self.budget)

    def handoff_adjacent(self, src: Mission, dst: Mission, claim: str) -> None:
        src.send_adjacent(src.picture.who_head_id, claim, peer_id=dst.id)
        dst.receive_adjacent(src.id, claim)

    def _brief(self, mission: Mission, function: str, extra: str = "", slot: Slot | None = None, picture: str | None = None, mode: str = "") -> Brief:
        """picture overrides the living picture. Workers get the split-time picture,
        so a sibling's delta never reaches their brief."""
        slot = slot or next(s for s in mission.picture.slots if s.function == function)
        if function == "verifier":
            crit = "; ".join(mission.picture.success_criteria)
            extra = (
                (extra + "\n") if extra else ""
            ) + (
                "VERIFIER RULE: claim MUST start with PASS or FAIL. "
                "PASS only if the product itself meets every success criterion. "
                "Your own evidence does not count toward a criterion. "
                f"Criteria: {crit}. Do not use the picture as the claim."
            )
        packet = self.store.scoped_brief(mission.id, extra, channel_id=slot.channel_id)
        return Brief(
            slot_function=slot.function,
            skill=slot.skill,
            packet=packet,
            effect=mission.picture.effect,
            purpose=mission.picture.purpose,
            picture=mission.picture.current_picture if picture is None else picture,
            end_state=mission.picture.end_state,
            channel_id=slot.channel_id or "",
            isolated=True,
            tools=list(slot.tools),
            success_criteria=list(mission.picture.success_criteria),
            mode=mode,
        )

    def _call(self, mission: Mission, brief: Brief, slot: Slot | None = None) -> Artifact:
        """One budgeted model call. The model runs outside the lock; the board inside it."""
        with self._lock:
            self._arm(mission)
            mission.assert_running()
            heard = _sibling_heard(mission, brief)
        started = time.perf_counter()
        art = self.adapter.act(brief)
        latency = time.perf_counter() - started
        usage = getattr(self.adapter, "last_usage", None) or {}
        prompt = usage.get("prompt_tokens") or max(1, len(brief.packet + brief.effect + brief.purpose + brief.picture) // 4)
        completion = usage.get("completion_tokens") or max(1, len(art.claim) // 4)
        usage_real = bool(usage.get("prompt_tokens") or usage.get("completion_tokens"))
        # The kernel names the channel, not the model.
        if brief.slot_function == "head":
            art.channel_id = "head-plan" if brief.mode == "plan" else "head-integrate"
        elif brief.slot_function == "verifier":
            art.channel_id = "verify"
        elif brief.channel_id:
            art.channel_id = brief.channel_id
        with self._lock:
            mission.adapter_name = getattr(self.adapter, "name", "") or mission.adapter_name
            mission.record_call({
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
                slot_id = slot.id if slot else mission.picture.who_head_id
                try:
                    mission.assert_tools(slot_id, toolish)
                except InvariantError as e:
                    mission.halt(e.message, code=e.code)
            b = mission.budget
            used = int(prompt) + int(completion)
            if b and used > b.max_tokens_per_call:
                mission.halt(f"max_tokens_per_call {b.max_tokens_per_call} exceeded ({used})")
            mission.assert_within_budget()
        return art

    def _act(self, mission: Mission, brief: Brief, slot: Slot | None = None) -> Artifact:
        """A call plus tool rounds. Allowed tools run, results come back in the next brief."""
        art = self._call(mission, brief, slot)
        for _ in range(self.max_tool_rounds):
            wanted = [r for r in art.requests if _tool_name(r) in RUNNABLE]
            if not wanted:
                return art
            results = []
            for req in wanted:
                out = self.toolbox.run(req)
                results.append(out)
                with self._lock:
                    mission._record("tool", {
                        "slot": slot.id if slot else brief.slot_function,
                        "channel": brief.channel_id,
                        "request": str(req)[:200],
                        "chars": len(out),
                    })
            brief = replace(brief, packet=f"{brief.packet}\n{TOOL_RESULTS}\n" + "\n\n".join(results))
            art = self._call(mission, brief, slot)
        if any(_tool_name(r) in RUNNABLE for r in art.requests):
            with self._lock:
                mission._record("tool_rounds_exhausted", {"slot": slot.id if slot else brief.slot_function})
        return art

    # --- task organization ---

    def _element_cost(self, seam: Seam) -> int:
        """Calls one element may spend: one, plus tool rounds if its specialty has tools."""
        runnable = any(t in RUNNABLE for t in QUAL_TOOLS.get(seam.skill, ()))
        return 1 + (self.max_tool_rounds if runnable else 0)

    def _assess(self, mission: Mission, seams: list[Seam]) -> list[Assessment]:
        b = mission.budget
        verdicts = assess(
            _first_per_channel(seams),
            world=getattr(mission, "world", None),
            occupied_channels=[s.channel_id for s in mission.picture.slots if s.channel_id],
            allow_split=getattr(b, "allow_split", True),
            pace=getattr(b, "pace", ""),
            calls_left=(b.max_calls - len(mission.calls)) if b else None,
            worker_slots_left=MAX_WORKERS - mission.picture.worker_count(),
            element_cost=self._element_cost,
        )
        for v in verdicts:
            mission._record("gate", v.as_dict())
        return verdicts

    def _staff(self, mission: Mission, legal: list[Assessment]) -> list[Slot]:
        head = mission.picture.who_head_id
        added = []
        for a in legal:
            worker = Slot(id=f"w-{a.seam.channel_id}", function="worker", skill=a.seam.skill, channel_id=a.seam.channel_id)
            mission.write_who(head, mission.picture.slots + [worker], gates=a.gates)
            added.append(worker)
        return added

    def _run_elements(self, mission: Mission, added: list[Slot], split_picture: str, notes: dict[str, str] | None = None) -> list[Artifact]:
        """Elements work at the same time, each blind to its siblings, then report in seam order.

        notes carries the lead's text from each seam to its element, so an element
        knows its part and not only its channel name.
        """

        def one(worker: Slot) -> Artifact:
            note = (notes or {}).get(worker.channel_id or "", "")
            brief = self._brief(
                mission, "worker",
                extra=f"channel={worker.channel_id} only. Do not see sibling channels."
                + (f" Lead's note for this element: {note}" if note else ""),
                slot=worker, picture=split_picture, mode="work",
            )
            return self._act(mission, brief, slot=worker)

        if self.parallel and len(added) > 1:
            with ThreadPoolExecutor(max_workers=len(added)) as pool:
                futures = [pool.submit(one, w) for w in added]
                arts = [f.result() for f in futures]
        else:
            arts = [one(w) for w in added]
        for worker, art in zip(added, arts):
            mission.accept_artifact(art)
            mission.post_delta(Delta(claim=art.delta_to_picture or art.claim, evidence=list(art.evidence), uncertainty=art.uncertainty, channel_id=art.channel_id, net="element"))
            self.store.remember_working(mission.id, f"channel:{worker.channel_id}", art.claim)
        return arts

    def _calls_left(self, mission: Mission) -> int:
        b = mission.budget
        return (b.max_calls - len(mission.calls)) if b else 1 << 30

    def _verify(self, mission: Mission, product: Artifact, *, adapt: bool) -> tuple[Artifact, bool]:
        """Check the product. On a failed check, adapt the method once if pace and budget allow."""
        head = mission.picture.who_head_id
        check = self._act(mission, self._brief(mission, "verifier", extra=product.claim, mode="verify"))
        verified = _verifier_accepts(check, mission, product)
        mission.accept_artifact(check)
        b = mission.budget
        if not verified and adapt and getattr(b, "allow_adapt", True) and self._calls_left(mission) >= 2:
            last = mission.last_verify or {}
            misses = list(last.get("misses", [])) + list(last.get("world_misses", []))
            mission.report_plan_wrong(f"verifier did not pass: {check.claim[:160]}; misses: {', '.join(misses) or 'none named'}")
            mission.respond_why(head, "plan-wrong", "CHANGE_METHOD", f"rework the product to meet: {'; '.join(mission.picture.success_criteria)}")
            product = self._act(mission, self._brief(
                mission, "head",
                extra=(
                    "REWORK. The verifier failed the last product. "
                    f"Misses: {', '.join(misses) or 'none named'}. Last product: {product.claim[:400]}"
                ),
                mode="rework",
            ))
            mission.accept_artifact(product)
            check = self._act(mission, self._brief(mission, "verifier", extra=product.claim, mode="verify"))
            verified = _verifier_accepts(check, mission, product)
            mission.accept_artifact(check)
        if not verified:
            mission.mark_stop_rule_failed("verifier")
            mission.halt("verifier did not PASS named success criteria")
        return product, verified

    def _propose(self, mission: Mission) -> list[Seam]:
        """The lead reads the situation and proposes elements. Strategies override this."""
        head = mission.picture.who_head_id
        mission.slide(head, head, "reason", "read the situation; propose elements only for independent work")
        plan = self._act(mission, self._brief(mission, "head", extra=PLAN_BRIEF.format(quals="|".join(QUALS)), mode="plan"))
        mission.accept_artifact(plan)
        return parse_seams(" ".join(plan.requests))

    def _judge(self, mission: Mission, seams: list[Seam]) -> list[Assessment]:
        """The gates. Strategies override this."""
        return self._assess(mission, seams)

    def _one_body_qual(self, verdicts: list[Assessment]) -> str:
        """One body cross-trains into what the work needs; with a workspace, that includes reading it."""
        single = next((v for v in verdicts if v.gate == "can_someone_else" and v.refused.startswith("one open seam")), None)
        workspace = bool(self.toolbox.roots or self.toolbox.files)
        qual = single.seam.skill if single else ("retrieve" if workspace else "draft")
        if workspace and not any(t in RUNNABLE for t in QUAL_TOOLS.get(qual, ())):
            qual = "retrieve"
        return qual

    @staticmethod
    def _account(verdicts: list[Assessment], added: list[Slot]) -> str:
        """The lead's answer to the operator, built from the gate record."""
        refused = [f"{v.seam.channel_id}: {v.refused}" for v in verdicts if not v.legal]
        if added:
            head = f"{len(added)} elements: {', '.join(w.channel_id or '' for w in added)}"
        elif verdicts:
            head = "one body"
        else:
            head = "one body: the lead proposed no independent parts"
        return head + (f"; refused {'; '.join(refused)}" if refused else "")

    def _close(self, mission: Mission, product: Artifact, operator_why: str, response: str, reason: str, out: str) -> str:
        head = mission.picture.who_head_id
        question = EchoWhy(operator_why).admit()
        note = mission.submit_why(question, "why-1")
        mission.respond_why(head, note.id, response, reason)
        moved = mission.ask_if_picture_moved()
        if moved and getattr(moved.status, "value", moved.status) == "open":
            mission.respond_why(head, moved.id, "KEEP_ROSTER", "purpose holds after the picture moved")
        mission.send_out(head, out)
        fire_auto_cues(mission)
        mission.complete()
        self.store.archive_episode(mission.id, mission.summary() | {"product": product.claim})
        return question

    # --- runs ---

    @_aborts_on_error
    def run_mission(self, mission: Mission, *, look_update: str, operator_why: str = "Could this have been one body?", axes: list[str] | None = None) -> LoopResult:
        """The lead reads the situation and organizes the team. The kernel judges it.

        1. Look. The lead proposes elements for independent parts (or none).
        2. Gates judge every proposal. Two or more legal elements: split, run them
           at the same time, regroup. Otherwise one body; if the one open part needs
           a specialty, the lead cross-trains into it.
        3. Verify. If the product fails and the pace allows, report the plan wrong,
           change the method, rework once.
        4. The operator's question is answered from the gate record.
        """
        self._arm(mission)
        mission.assert_running()
        head = mission.picture.who_head_id
        mission.update_context(head, look_update)
        self.store.remember_working(mission.id, "look", look_update)

        verdicts = self._judge(mission, self._propose(mission))
        legal = [v for v in verdicts if v.legal]

        added: list[Slot] = []
        if len(legal) >= self.min_split:
            mission.set_how(head, "elements: " + ", ".join(v.seam.channel_id for v in legal), axes or ["parallel", "fan_in"])
            split_picture = mission.picture.current_picture
            added = self._staff(mission, legal)
            self._run_elements(mission, added, split_picture, notes={v.seam.channel_id: v.seam.named_failure for v in legal})
            # Parts refused for capacity or a malformed proposal still need doing: the lead covers them.
            leftover = [v.seam.channel_id for v in verdicts if v.gate in ("should_we", "could_we")]
            extra = "REGROUP. Integrate the element products against the intent. Do not invent what an element did not report."
            if leftover:
                mission.slide(head, head, self._one_body_qual([]), "regroup and cover parts no element took")
                extra += f" These parts got no element and are yours to cover: {', '.join(leftover)}."
            else:
                mission.slide(head, head, "reason", "regroup: integrate element products")
            product = self._act(mission, self._brief(mission, "head", extra=extra, mode="integrate"))
        else:
            qual = self._one_body_qual(verdicts)
            mission.set_how(head, f"one body: {qual}", axes or ["sequential"])
            mission.slide(head, head, qual, "one body does the work")
            product = self._act(mission, self._brief(mission, "head", extra="WORK. Do the work yourself, one body.", mode="work"))
        mission.accept_artifact(product)
        self.store.remember_working(mission.id, "product", product.claim)

        product, verified = self._verify(mission, product, adapt=True)
        reason = self._account(verdicts, added)
        question = self._close(mission, product, operator_why, "KEEP_ROSTER", reason, f"workers={len(added)}; effect={mission.picture.effect}")
        return LoopResult(
            mission=mission, product=product, verified=verified, why_question=question,
            why_response="KEEP_ROSTER", split=bool(added), channels=[w.channel_id or "" for w in added],
            verdicts=verdicts,
        )

    @_aborts_on_error
    def run_standing_order(self, mission: Mission, *, look_update: str, operator_why: str, head_response: str = "KEEP_ROSTER", head_reason: str = "goal still valid; keep the roster") -> LoopResult:
        self._arm(mission)
        mission.assert_running()
        head = mission.picture.who_head_id
        mission.update_context(head, look_update)
        self.store.remember_working(mission.id, "look", look_update)
        mission.slide(head, head, "draft", "write the default task")
        product = self._act(mission, self._brief(mission, "head", extra="write default task", mode="work"))
        mission.accept_artifact(product)
        self.store.remember_working(mission.id, "product", product.claim)
        product, verified = self._verify(mission, product, adapt=False)
        question = self._close(mission, product, operator_why, head_response, head_reason, f"status={mission.status.value}; effect={mission.picture.effect}")
        return LoopResult(mission=mission, product=product, verified=verified, why_question=question, why_response=head_response, split=False, channels=[])

    @_aborts_on_error
    def run_multi_axis(self, mission: Mission, *, look_update: str, seams: list[Seam], axes: list[str], operator_why: str, head_response: str = "CHANGE_METHOD", head_reason: str = "seams are independent; How is multi-axis") -> LoopResult:
        """Operator names the seams. The same gates judge them as judge the lead's."""
        self._arm(mission)
        mission.assert_running()
        if mission.budget and not getattr(mission.budget, "allow_split", True):
            mission.halt(f"pace {getattr(mission.budget, 'pace', '?')} cannot split")
        head = mission.picture.who_head_id
        mission.update_context(head, look_update)
        self.store.remember_working(mission.id, "look", look_update)
        mission.slide(head, head, "reason", "choose How against the picture")
        mission.set_how(head, "multi-axis", axes)
        verdicts = self._assess(mission, seams)
        split_picture = mission.picture.current_picture
        legal = [v for v in verdicts if v.legal]
        added = self._staff(mission, legal)
        self._run_elements(mission, added, split_picture, notes={v.seam.channel_id: v.seam.named_failure for v in legal})
        integrate = self._act(mission, self._brief(mission, "head", extra="integrate isolated artifacts; do not invent seams", mode="integrate"))
        mission.accept_artifact(integrate)
        integrate, verified = self._verify(mission, integrate, adapt=False)
        if added:
            mission.send_adjacent(head, f"element {mission.id} holding {len(added)} channels", peer_id="peer-element")
        question = self._close(mission, integrate, operator_why, head_response, head_reason, f"split={len(added)}; effect={mission.picture.effect}")
        return LoopResult(mission=mission, product=integrate, verified=verified, why_question=question, why_response=head_response, split=len(added) > 0, channels=[w.channel_id or "" for w in added], verdicts=verdicts)

    @_aborts_on_error
    def adapt_vector(self, mission: Mission, *, look_update: str, report: str, new_method: str, axes: list[str], operator_why: str = "Confirm the new vector serves intent") -> LoopResult:
        self._arm(mission)
        mission.assert_running()
        if mission.budget and not getattr(mission.budget, "allow_adapt", True):
            mission.halt(f"pace {getattr(mission.budget, 'pace', '?')} cannot adapt")
        head = mission.picture.who_head_id
        mission.update_context(head, look_update)
        self.store.remember_working(mission.id, "look", look_update)
        mission.report_plan_wrong(report)
        mission.respond_why(head, "plan-wrong", "CHANGE_METHOD", new_method)
        mission.set_how(head, new_method, axes)
        mission.slide(head, head, "draft", f"execute {new_method}")
        product = self._act(mission, self._brief(mission, "head", extra=f"new vector: {new_method}", mode="work"))
        mission.accept_artifact(product)
        product, verified = self._verify(mission, product, adapt=False)
        question = self._close(mission, product, operator_why, "KEEP_ROSTER", "vector already changed; hold the new How", f"vector={new_method}; effect={mission.picture.effect}")
        return LoopResult(mission=mission, product=product, verified=verified, why_question=question, why_response="KEEP_ROSTER", split=False, channels=[])
