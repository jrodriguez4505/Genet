"""Qualifications: what each specialty is for.

A slot carries one active qual. The lead can slide its own qual (cross-training);
an element is created with the qual its seam names (a specialist). The role text
goes into the model's system prompt; the tool allowlist is QUAL_TOOLS.
"""

from __future__ import annotations

from .models import QUAL_TOOLS

ROLE = {
    "execute": "Do the assigned piece of work and report the result.",
    "retrieve": (
        "You find source material. Search before you claim. "
        "Put file paths and quoted lines you relied on in evidence."
    ),
    "reason": "You work the problem through. State the steps that carry the conclusion.",
    "draft": "You write the product the effect asks for, in the form the end state needs.",
    "simulate": "You run the plan forward and report where it breaks and what that costs.",
    "observe": (
        "You survey what exists. List and read; report what is there, not what should be. "
        "Put file paths in evidence."
    ),
    "verify": "You judge the product against the success criteria. Your claim starts with PASS or FAIL.",
}


def role(qual: str) -> str:
    return ROLE.get(qual, ROLE["execute"])


def tools(qual: str) -> tuple[str, ...]:
    return tuple(QUAL_TOOLS.get(qual, ("write",)))
