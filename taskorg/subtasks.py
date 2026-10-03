"""Sub-tasks are explicit marks in the context, never inferred."""

from __future__ import annotations

from .gates import Subtask


def parse_subtasks(text: str) -> list[Subtask]:
    """
    Read tagged sub-tasks from a context string or a lead's proposals.

    Format: subtask:<channel>[@<skill>]=<named_failure>
    Underscores in the failure read as spaces. skill defaults to execute.
    Example: 'Primary blocked. subtask:source-a@retrieve=notes_must_not_mix subtask:source-b=independent_b'
    """
    found: list[Subtask] = []
    for token in text.replace(",", " ").split():
        if not token.startswith("subtask:"):
            continue
        subtask = parse_subtask(token[len("subtask:") :])
        if subtask:
            found.append(subtask)
    return found


def parse_subtask(body: str) -> Subtask | None:
    """<channel>[@<skill>]=<named_failure>, without the subtask: prefix."""
    if "=" not in body:
        return None
    spec, failure = body.split("=", 1)
    channel, _, skill = spec.partition("@")
    channel = channel.strip()
    failure = failure.strip().replace("_", " ")
    if not channel or not failure:
        return None
    return Subtask(channel, failure, skill=skill.strip().lower() or "execute")
