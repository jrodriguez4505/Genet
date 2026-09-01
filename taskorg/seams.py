"""Seams are explicit marks in context, not inferred theater."""

from .gates import Seam


def parse_seams(picture: str) -> list[Seam]:
    """
    Read tagged seams from a picture string.

    Format: seam:<channel>=<named failure>
    Example: 'Primary blocked. seam:source-a=independent source-a seam:source-b=independent source-b'
    """
    found: list[Seam] = []
    for token in picture.replace(",", " ").split():
        if not token.startswith("seam:"):
            continue
        body = token[len("seam:") :]
        if "=" not in body:
            continue
        channel, failure = body.split("=", 1)
        channel = channel.strip()
        failure = failure.strip().replace("_", " ")
        if channel and failure:
            found.append(Seam(channel, failure))
    return found
