from __future__ import annotations

import time
from dataclasses import dataclass

from .adapters import Brief, EchoWhy, ModelAdapter, StubAdapter
from .budget import Budget
from .cues import fire_auto_cues
from .gates import Seam, decide
from .memory_store import MemoryStore
from .mission import Mission
from .models import Artifact, Delta, Slot


def score_criteria(product: Artifact | None, check: Artifact, criteria: list[str]) -> dict:
    parts = [check.claim, *check.evidence]
    if product:
        parts.extend([product.claim, *product.evidence])
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
        scored = score_criteria(product, check, mission.picture.success_criteria)
        scored["world_misses"] = ["claim is not PASS"]
        mission.last_verify = scored
        return False
    scored = score_criteria(product, check, mission.picture.success_criteria)
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


class Engine:
    def __init__(self, store: MemoryStore, adapter: ModelAdapter | None = None, budget: Budget | None = None):
        self.store = store
        self.adapter = adapter or StubAdapter()
        self.budget = budget or Budget()

    def _arm(self, mission: Mission) -> None:
        if mission.budget is None:
            mission.attach_budget(self.budget)

    def handoff_adjacent(self, src: Mission, dst: Mission, claim: str) -> None:
        src.send_adjacent(src.picture.who_head_id, claim, peer_id=dst.id)
        dst.receive_adjacent(src.id, claim)

    def _brief(self, mission: Mission, function: str, extra: str = "", slot: Slot | None = None) -> Brief:
        slot = slot or next(s for s in mission.picture.slots if s.function == function)
        if function == "verifier":
            crit = "; ".join(mission.picture.success_criteria)
            extra = ((extra + "\n") if extra else "") + (
                "VERIFIER RULE: claim MUST start with PASS or FAIL. "
                "PASS only if every success criterion appears in the product or your evidence. "
                f"Criteria: {crit}. Do not use the picture as the claim."
            )
        packet = self.store.scoped_brief(mission.id, extra, channel_id=slot.channel_id)
        return Brief(
            slot_function=slot.function,
            skill=slot.skill,
            packet=packet,
            effect=mission.picture.effect,
            purpose=mission.picture.purpose,
            picture=mission.picture.current_picture,
            end_state=mission.picture.end_state,
            channel_id=slot.channel_id or "",
            isolated=True,
            tools=list(slot.tools),
            success_criteria=list(mission.picture.success_criteria),
        )

    def _act(self, mission: Mission, brief: Brief, slot: Slot | None = None):
        self._arm(mission)
        mission.assert_running()
        started = time.perf_counter()
        art = self.adapter.act(brief)
        if art.requests:
            slot_id = slot.id if slot else mission.picture.who_head_id
            known = {"write", "verify", "observe", "search", "read", "retrieve", "spawn"}
            toolish = [r for r in art.requests if str(r).strip().lower() in known]
            if toolish:
                try:
                    mission.assert_tools(slot_id, toolish)
                except Exception as e:
                    mission.halt(str(e))
                    raise
        latency = time.perf_counter() - started
        usage = getattr(self.adapter, "last_usage", None) or {}
        prompt = usage.get("prompt_tokens") or max(1, len(brief.packet + brief.effect + brief.purpose + brief.picture) // 4)
        completion = usage.get("completion_tokens") or max(1, len(art.claim) // 4)
        mission.adapter_name = getattr(self.adapter, "name", "") or mission.adapter_name
        usage_real = bool(usage.get("prompt_tokens") or usage.get("completion_tokens"))
        mission.record_call({
            "slot": (slot.id if slot else brief.slot_function),
            "function": brief.slot_function,
            "channel": brief.channel_id or brief.slot_function,
            "latency_s": round(latency, 4),
            "prompt_tokens": int(prompt),
            "completion_tokens": int(completion),
            "packet": brief.packet,
            "adapter": getattr(self.adapter, "name", ""),
            "tokens_estimated": not usage_real,
        })
        b = mission.budget
        used = int(prompt) + int(completion)
        if b and used > b.max_tokens_per_call:
            mission.halt(f"max_tokens_per_call {b.max_tokens_per_call} exceeded ({used})")
        mission.assert_running()
        return art

    def run_standing_order(self, mission: Mission, *, look_update: str, operator_why: str, head_response: str = "KEEP_ROSTER", head_reason: str = "goal still valid; keep the roster") -> LoopResult:
        self._arm(mission)
        mission.assert_running()
        head = mission.picture.who_head_id
        mission.update_context(head, look_update)
        self.store.remember_working(mission.id, "look", look_update)
        mission.slide(head, head, "draft", "write the default task")
        product = self._act(mission, self._brief(mission, "head", extra="write default task"))
        mission.accept_artifact(product)
        self.store.remember_working(mission.id, "product", product.claim)
        check = self._act(mission, self._brief(mission, "verifier", extra=product.claim))
        verified = _verifier_accepts(check, mission, product)
        mission.accept_artifact(check)
        if not verified:
            mission.mark_stop_rule_failed("verifier")
            mission.halt("verifier did not PASS named success criteria")
        question = EchoWhy(operator_why).admit()
        note = mission.submit_why(question, "why-1")
        mission.respond_why(head, note.id, head_response, head_reason)
        moved = mission.ask_if_picture_moved()
        if moved and getattr(moved.status, "value", moved.status) == "open":
            mission.respond_why(head, moved.id, "KEEP_ROSTER", "purpose holds after the picture moved")
        mission.send_out(head, f"status={mission.status.value}; effect={mission.picture.effect}")
        fire_auto_cues(mission)
        mission.complete()
        self.store.archive_episode(mission.id, mission.summary() | {"product": product.claim})
        return LoopResult(mission=mission, product=product, verified=verified, why_question=question, why_response=head_response, split=False, channels=[])

    def run_multi_axis(self, mission: Mission, *, look_update: str, seams: list[Seam], axes: list[str], operator_why: str, head_response: str = "CHANGE_METHOD", head_reason: str = "seams are independent; How is multi-axis") -> LoopResult:
        self._arm(mission)
        mission.assert_running()
        if mission.budget and not getattr(mission.budget, "allow_split", True):
            mission.halt(f"pace {getattr(mission.budget, 'pace', '?')} cannot split")
        head = mission.picture.who_head_id
        mission.update_context(head, look_update)
        self.store.remember_working(mission.id, "look", look_update)
        mission.slide(head, head, "reason", "choose How against the picture")
        mission.set_how(head, "multi-axis", axes)
        added: list[Slot] = []
        remaining = list(seams)
        slots = list(mission.picture.slots)
        while remaining:
            mission.assert_running()
            occupied = [s.channel_id for s in mission.picture.slots if s.channel_id]
            rec = decide(remaining, world=getattr(mission, "world", None), occupied_channels=occupied)
            if rec is None:
                break
            worker = Slot(id=f"w-{rec.channel_id}", function="worker", skill="execute", channel_id=rec.channel_id)
            slots = slots + [worker]
            mission.write_who(head, slots, gates=rec)
            added.append(worker)
            remaining = [s for s in remaining if s.channel_id != rec.channel_id]
        for worker in added:
            art = self._act(mission, self._brief(mission, "worker", extra=f"channel={worker.channel_id} only. Do not see sibling channels.", slot=worker), slot=worker)
            art.channel_id = worker.channel_id or art.channel_id
            mission.accept_artifact(art)
            mission.post_delta(Delta(claim=art.delta_to_picture or art.claim, evidence=list(art.evidence), uncertainty=art.uncertainty, channel_id=art.channel_id, net="element"))
            self.store.remember_working(mission.id, f"channel:{worker.channel_id}", art.claim)
        integrate = self._act(mission, self._brief(mission, "head", extra="integrate isolated artifacts; do not invent seams"))
        mission.accept_artifact(integrate)
        check = self._act(mission, self._brief(mission, "verifier", extra=integrate.claim))
        verified = _verifier_accepts(check, mission, integrate)
        mission.accept_artifact(check)
        if not verified:
            mission.mark_stop_rule_failed("verifier")
            mission.halt("verifier did not PASS named success criteria")
        fire_auto_cues(mission)
        question = EchoWhy(operator_why).admit()
        note = mission.submit_why(question, "why-1")
        mission.respond_why(head, note.id, head_response, head_reason)
        moved = mission.ask_if_picture_moved()
        if moved and getattr(moved.status, "value", moved.status) == "open":
            mission.respond_why(head, moved.id, "KEEP_ROSTER", "purpose holds after the picture moved")
        mission.send_out(head, f"split={len(added)}; effect={mission.picture.effect}")
        if added:
            mission.send_adjacent(head, f"element {mission.id} holding {len(added)} channels", peer_id="peer-element")
        mission.complete()
        self.store.archive_episode(mission.id, mission.summary() | {"product": integrate.claim})
        return LoopResult(mission=mission, product=integrate, verified=verified, why_question=question, why_response=head_response, split=len(added) > 0, channels=[w.channel_id or "" for w in added])

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
        product = self._act(mission, self._brief(mission, "head", extra=f"new vector: {new_method}"))
        mission.accept_artifact(product)
        check = self._act(mission, self._brief(mission, "verifier", extra=product.claim))
        verified = _verifier_accepts(check, mission, product)
        mission.accept_artifact(check)
        if not verified:
            mission.mark_stop_rule_failed("verifier")
            mission.halt("verifier did not PASS named success criteria")
        question = EchoWhy(operator_why).admit()
        note = mission.submit_why(question, "why-1")
        mission.respond_why(head, note.id, "KEEP_ROSTER", "vector already changed; hold the new How")
        moved = mission.ask_if_picture_moved()
        if moved and getattr(moved.status, "value", moved.status) == "open":
            mission.respond_why(head, moved.id, "KEEP_ROSTER", "purpose holds after the picture moved")
        mission.send_out(head, f"vector={new_method}; effect={mission.picture.effect}")
        fire_auto_cues(mission)
        mission.complete()
        self.store.archive_episode(mission.id, mission.summary() | {"product": product.claim})
        return LoopResult(mission=mission, product=product, verified=verified, why_question=question, why_response="KEEP_ROSTER", split=False, channels=[])
