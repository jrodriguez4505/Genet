"""Skills: what each one is for.

A slot carries one active skill. The lead can switch its own skill; a sub-agent
is created with the skill its sub-task names (a specialist). The brief text goes
into the model's system prompt; the tool allowlist is SKILL_TOOLS.
"""

from __future__ import annotations

from .models import SKILL_TOOLS

BRIEFS = {
    "execute": "Do the assigned piece of work and report the result.",
    "retrieve": (
        "You find source material. Search before you claim. "
        "Put file paths and quoted lines you relied on in evidence."
    ),
    "reason": "You work the problem through. State the steps that carry the conclusion.",
    "draft": "You write the product the goal asks for, in the form the done-when condition needs.",
    "simulate": "You run the plan forward and report where it breaks and what that costs.",
    "observe": (
        "You survey what exists. List and read; report what is there, not what should be. "
        "Put file paths in evidence."
    ),
    "verify": "You judge the product against the success criteria. Your claim starts with PASS or FAIL.",
}


def brief(skill: str) -> str:
    return BRIEFS.get(skill, BRIEFS["execute"])


def tools(skill: str) -> tuple[str, ...]:
    return tuple(SKILL_TOOLS.get(skill, ("write",)))
