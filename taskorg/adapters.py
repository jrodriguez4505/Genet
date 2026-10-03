from __future__ import annotations

from dataclasses import dataclass

from .models import Artifact

TOOL_RESULTS = "TOOL RESULTS"


@dataclass
class Brief:
    slot_function: str
    skill: str
    packet: str
    effect: str
    purpose: str
    picture: str
    end_state: str
    channel_id: str = ""
    isolated: bool = True
    tools: list[str] | None = None
    success_criteria: list[str] | None = None
    # What this call is for: plan | work | integrate | rework | verify. "" for older flows.
    mode: str = ""


class ModelAdapter:
    """Models sit behind the graph. They return text or a structured artifact."""

    name = "base"

    def act(self, brief: Brief) -> Artifact:
        raise NotImplementedError


class StubAdapter(ModelAdapter):
    """Deterministic stand-in for a compliant model. No network. Predictable fixtures.

    It plans by proposing the seams the picture tags, uses a runnable tool once
    when its qualification has one, and addresses the criteria in its product.
    """

    name = "stub"

    def act(self, brief: Brief) -> Artifact:
        tool = self._tool_request(brief)
        if tool:
            return Artifact(
                claim=f"Looking first: {tool}",
                evidence=[],
                uncertainty="waiting on tool results",
                channel_id=brief.channel_id or brief.slot_function,
                delta_to_picture="",
                requests=[tool],
            )
        evidence = ["stub-adapter", brief.packet[:120]]
        found = self._first_tool_line(brief)
        if found:
            evidence.append(found)
        requests: list[str] = []
        if brief.slot_function == "head" and brief.mode == "plan":
            tagged = [t for t in brief.picture.replace(",", " ").split() if t.startswith("seam:")]
            claim = (
                f"Read: {len(tagged)} independent part(s) named in the picture."
                if tagged
                else "Read: one body is enough; nothing in the picture is independent."
            )
            requests = tagged
            channel = "head-plan"
        elif brief.slot_function == "head":
            # A compliant model addresses the criteria in the product itself.
            criteria = "; ".join(brief.success_criteria or [])
            claim = (
                f"Default task: {brief.effect}. "
                f"Purpose holds: {brief.purpose}. "
                f"Picture: {brief.picture}. Method: look, then write."
                + (f" Covers: {criteria}." if criteria else "")
            )
            channel = "head-integrate"
        elif brief.slot_function == "verifier":
            claim = "PASS — effect named, purpose intact, picture updated."
            channel = "verify"
        else:
            vantage = brief.channel_id or brief.skill or "execute"
            claim = (
                f"[{vantage}] Isolated product against '{brief.effect}'. "
                f"This channel does not see sibling Workers. "
                f"Intent: {brief.purpose}."
            )
            channel = vantage
        return Artifact(
            claim=claim,
            evidence=evidence,
            uncertainty="stub has no external sources",
            channel_id=channel,
            delta_to_picture=f"stub picture after {brief.slot_function}: {brief.effect}",
            requests=requests,
        )

    @staticmethod
    def _tool_request(brief: Brief) -> str:
        """One tool round when the qualification has a runnable tool and none has run yet."""
        if TOOL_RESULTS in brief.packet:
            return ""
        tools = brief.tools or []
        if "retrieve" in tools:
            query = brief.channel_id or (brief.effect.split() or ["notes"])[-1]
            return f"retrieve:{query}"
        if "observe" in tools:
            return "observe"
        return ""

    @staticmethod
    def _first_tool_line(brief: Brief) -> str:
        if TOOL_RESULTS not in brief.packet:
            return ""
        after = brief.packet.split(TOOL_RESULTS, 1)[1].strip().splitlines()
        lines = [ln for ln in after if ln.strip() and not ln.startswith("[")]
        return lines[0][:200] if lines else ""


class EchoWhy:
    """Operator / fixture voice in the Why slot."""

    def __init__(self, question: str):
        self.question = question

    def admit(self) -> str:
        return self.question
