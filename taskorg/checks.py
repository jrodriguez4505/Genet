"""What the verifier reads the product against: the view it is given and the sources the kernel opens for it.

The verifier is the one member whose work is to disagree with the author. Two things let it
(docs/TEAM_DESIGN.md). It can be shown the sources, so it checks the product against them rather than
trusting it. It can be kept from the author's notes, so a mistake the author made from a note does not
reach the verifier along with the note.

Views:

  shared       the brief every member gets: the shared context, with every reply's context_update
               merged in, and all of working memory
  independent  the context as the operator gave it, and working memory without the product or any
               sub-agent's report: the goal, the criteria, the product and its evidence, and nothing else
               of the author's

The kernel, not the author and not the verifier, picks the files to open:

  none     no sources: the verifier reads the product alone
  full     every file the goal names, the product cites, its uncertainty names, or the run read
  layered  the files most likely to be wrong, then a few at random:
           1. a file the goal names that no call in the run read or searched. The product has
              something for its subject, and it came from somewhere else.
           2. a file the product's uncertainty names
           3. SAMPLE more, drawn from what the goal names or the product cites, so the author cannot
              know which ones will be checked

The picks come from the run's own record and the product's text, so the same product always opens the
same files, and a tape replays. With sources on, the kernel also checks for nothing that every evidence
quote is in the file it cites, and tells the verifier which are not.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable
from pathlib import Path

from .models import Artifact

VIEWS = ("shared", "independent")
SOURCES = ("none", "layered", "full")
# Working facts an independent verifier keeps: the operator's context and the files the operator attached.
INDEPENDENT_FACTS = ("context", "reads")
SAMPLE = 2          # files the layered check draws at random
MAX_SOURCES = 24    # files one check opens at most; the per-call limit may trim it further
MIN_QUOTE = 12      # characters a quote needs before the kernel checks it

SOURCES_HEAD = "SOURCES (opened by the kernel for this check; the author did not choose them)"
SOURCE_RULE = (
    "SOURCE RULE: the files under SOURCES are the workspace's own. Where the product states a fact that one "
    "of them covers, that file must support it for the same subject and period. If one does not, FAIL and "
    "name the fact and the file."
)

_READ_HEAD = re.compile(r"\[read ([^\]\n]+)\](?:\n| already in full above)")
_MATCH_LINE = re.compile(r"^([^\[\n:][^\n:]*):\d+: ", re.MULTILINE)
_QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")
_ELLIPSIS = re.compile(r"\.{3}|…")


def files_in_result(out: str) -> dict[str, list[str]]:
    """The files a tool result shows, by the names the model sees: one it read, or those a search
    returned lines from. The kernel keeps them on the record, so a check knows what the run saw."""
    m = _READ_HEAD.match(out)
    if m:
        return {"read": [m.group(1).strip()]}
    if out.startswith("[retrieve"):
        found = list(dict.fromkeys(p.strip() for p in _MATCH_LINE.findall(out)))
        return {"matched": found} if found else {}
    return {}


def seen_files(run, kinds: tuple[str, ...] = ("read", "matched")) -> set[str]:
    """Files any call in the run read, or, with matched, any search returned lines from."""
    return {
        name
        for e in run.log
        if e.event == "tool"
        for kind in kinds
        for name in (e.detail.get(kind) or [])
    }


def _words(name: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", Path(name).stem.lower()) if w]


def named_in(text: str, names: Iterable[str]) -> list[str]:
    """Files whose subject the text names: the words of the file's stem, in order, as words of the text.
    Longest stem first, so Saffron Grid Partners is not also read as Saffron Grid. In order of mention."""
    low = (text or "").lower()
    taken: list[tuple[int, int]] = []
    first: dict[str, int] = {}
    for name in sorted(dict.fromkeys(names), key=lambda n: (-len(Path(n).stem), n)):
        words = _words(name)
        if sum(map(len, words)) < 3:
            continue
        rx = re.compile(r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(map(re.escape, words)) + r"(?![a-z0-9])")
        for m in rx.finditer(low):
            if not any(a < m.end() and m.start() < b for a, b in taken):
                taken.append((m.start(), m.end()))
                first.setdefault(name, m.start())
    return sorted(first, key=lambda n: (first[n], n))


def cited_in(text: str, names: Iterable[str]) -> list[str]:
    """Files the text names by file name, such as orbrook.md, in order of mention."""
    low = (text or "").lower()
    first: dict[str, int] = {}
    for name in dict.fromkeys(names):
        for form in dict.fromkeys((name.lower(), Path(name).name.lower())):
            m = re.search(r"(?<![\w.-])" + re.escape(form) + r"(?![\w-])", low)
            if m:
                first[name] = min(first.get(name, m.start()), m.start())
    return sorted(first, key=lambda n: (first[n], n))


def pick(run, product: Artifact, names: list[str], mode: str, *, sample: int = SAMPLE) -> list[tuple[str, str]]:
    """The files a check opens, each with why, in the order they are shown. See the module docstring."""
    if mode not in SOURCES:
        raise ValueError(f"sources must be one of {SOURCES}, got {mode!r}")
    if mode == "none" or not names:
        return []
    goal = named_in(run.state.goal, names)
    cited = cited_in(" ".join([product.claim, *product.evidence]), names)
    unsure = cited_in(product.uncertainty, names)
    picks: dict[str, str] = {}
    if mode == "full":
        for name in goal:
            picks.setdefault(name, "the goal names it")
        for name in cited:
            picks.setdefault(name, "the product cites it")
        for name in unsure:
            picks.setdefault(name, "the product's uncertainty names it")
        for name in sorted(seen_files(run, ("read",)) & set(names)):
            picks.setdefault(name, "the run read it")
        return list(picks.items())[:MAX_SOURCES]
    seen = seen_files(run)
    for name in goal:
        if name not in seen:
            picks.setdefault(name, "the goal names it, and no call in the run read or searched it")
    for name in unsure:
        picks.setdefault(name, "the product's uncertainty names it")
    rest = [n for n in dict.fromkeys(goal + cited) if n not in picks]
    # Seeded by the goal and the product, not the run: the same product opens the same files in every setup.
    rng = random.Random(f"{run.state.goal}\n{product.claim}")
    for name in rng.sample(rest, min(max(0, sample), len(rest))):
        picks.setdefault(name, "drawn at random")
    return list(picks.items())[:MAX_SOURCES]


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def misquoted(toolbox, product: Artifact, names: list[str]) -> list[str]:
    """Evidence whose quote is not in the file it cites. Checked in code, for nothing. A paraphrase is
    flagged too, so the verifier is told and judges; the kernel does not fail the product on this alone."""
    out = []
    for item in product.evidence:
        files = cited_in(item, names)
        quotes = _QUOTED.findall(item)
        if not files or not quotes:
            continue
        text = toolbox.text_of(files[0])
        if text is None:
            continue
        body = _norm(text)
        pieces = [p.strip(" .,;:") for q in quotes for p in _ELLIPSIS.split(q)]
        if any(len(p) >= MIN_QUOTE and _norm(p) not in body for p in pieces):
            out.append(f"{files[0]}: {item[:160]}")
    return out


def source_block(toolbox, name: str, why: str) -> str:
    return f"(picked: {why})\n{toolbox.read(name)}"
