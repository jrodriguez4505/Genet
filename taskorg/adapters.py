from __future__ import annotations

from dataclasses import dataclass

from .models import Artifact

TOOL_RESULTS = "TOOL RESULTS"


@dataclass
class Brief:
    slot_function: str
    skill: str
    packet: str
    goal: str
    purpose: str
    context: str
    done_when: str
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

    It plans by proposing the sub-tasks the context tags, uses a runnable tool once
    when its skill has one, and addresses the criteria in its product.
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
                context_update="",
                requests=[tool],
            )
        evidence = ["stub-adapter", brief.packet[:120]]
        found = self._first_tool_line(brief)
        if found:
            evidence.append(found)
        requests: list[str] = []
        if brief.slot_function == "lead" and brief.mode == "plan":
            tagged = [t for t in brief.context.replace(",", " ").split() if t.startswith("subtask:")]
            claim = (
                f"Read: {len(tagged)} independent part(s) named in the context."
                if tagged
                else "Read: one agent is enough; nothing in the context is independent."
            )
            requests = tagged
            channel = "lead-plan"
        elif brief.slot_function == "lead":
            # A compliant model addresses the criteria in the product itself.
            criteria = "; ".join(brief.success_criteria or [])
            claim = (
                f"Default task: {brief.goal}. "
                f"Purpose holds: {brief.purpose}. "
                f"Context: {brief.context}. Method: read, then write."
                + (f" Covers: {criteria}." if criteria else "")
            )
            channel = "lead-merge"
        elif brief.slot_function == "verifier":
            claim = "PASS — goal named, purpose intact, context updated."
            channel = "verify"
        else:
            vantage = brief.channel_id or brief.skill or "execute"
            claim = (
                f"[{vantage}] Isolated product against '{brief.goal}'. "
                f"This channel does not see sibling Workers. "
                f"Purpose: {brief.purpose}."
            )
            channel = vantage
        return Artifact(
            claim=claim,
            evidence=evidence,
            uncertainty="stub has no external sources",
            channel_id=channel,
            context_update=f"stub context after {brief.slot_function}: {brief.goal}",
            requests=requests,
        )

    @staticmethod
    def _tool_request(brief: Brief) -> str:
        """One tool round when the skill has a runnable tool and none has run yet."""
        if TOOL_RESULTS in brief.packet:
            return ""
        tools = brief.tools or []
        if "retrieve" in tools:
            query = brief.channel_id or (brief.goal.split() or ["notes"])[-1]
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


class OperatorQuestion:
    """The operator's question to the lead, recorded as a review."""

    def __init__(self, question: str):
        self.question = question

    def admit(self) -> str:
        return self.question
