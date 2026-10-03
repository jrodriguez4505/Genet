"""Seams are explicit marks in Where, not inferred theater."""

from __future__ import annotations

from .gates import Seam


def parse_seams(picture: str) -> list[Seam]:
    """
    Read tagged seams from a picture string.

    Format: seam:<channel>[@<qual>]=<named_failure>
    Underscores in the failure read as spaces. qual defaults to execute.
    Example: 'Primary blocked. seam:source-a@retrieve=notes_must_not_mix seam:source-b=independent_b'
    """
    found: list[Seam] = []
    for token in picture.replace(",", " ").split():
        if not token.startswith("seam:"):
            continue
        seam = parse_seam(token[len("seam:") :])
        if seam:
            found.append(seam)
    return found


def parse_seam(body: str) -> Seam | None:
    """<channel>[@<qual>]=<named_failure>, without the seam: prefix."""
    if "=" not in body:
        return None
    head, failure = body.split("=", 1)
    channel, _, skill = head.partition("@")
    channel = channel.strip()
    failure = failure.strip().replace("_", " ")
    if not channel or not failure:
        return None
    return Seam(channel, failure, skill=skill.strip().lower() or "execute")
