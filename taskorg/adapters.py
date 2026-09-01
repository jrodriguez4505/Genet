from __future__ import annotations

from dataclasses import dataclass

from .models import Artifact


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


class ModelAdapter:
    """Models sit behind the graph. They return text or a structured artifact."""

    name = "base"

    def act(self, brief: Brief) -> Artifact:
        raise NotImplementedError


class StubAdapter(ModelAdapter):
    """Deterministic stand-in. No network. Predictable fixtures."""

    name = "stub"

    def act(self, brief: Brief) -> Artifact:
        if brief.slot_function == "head":
            claim = (
                f"Default task: {brief.effect}. "
                f"Purpose holds: {brief.purpose}. "
                f"Picture: {brief.picture}. Method: look, then write."
            )
            channel = "head-integrate"
        elif brief.slot_function == "verifier":
            criteria = "; ".join(getattr(brief, "success_criteria", []) or [])
            claim = (
                "PASS — effect named, purpose intact, picture updated."
                + (f" Success criteria: {criteria}." if criteria else "")
            )
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
            evidence=["stub-adapter", brief.packet[:120]],
            uncertainty="stub has no external sources",
            channel_id=channel,
            delta_to_picture=f"stub picture after {brief.slot_function}: {brief.effect}",
            requests=[],
        )


class EchoWhy:
    """Operator / fixture voice in the review slot."""

    def __init__(self, question: str):
        self.question = question

    def admit(self) -> str:
        return self.question
