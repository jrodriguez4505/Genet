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
# The verifier told what a layered pick is: a figure no source covers is no reason to FAIL.
SAMPLE_RULE = (
    " These files are a sample: the kernel opened only some of what the product draws on. A fact that no file "
    "here covers is not a fault, so do not FAIL a product because a figure could not be confirmed or a file was "
    "not opened. FAIL for a fact a file here contradicts, or a product that does not answer the goal."
)
# How to read a source's undated line: half the failures of right merges cited one.
HEADING_RULE = (
    " A file's heading applies to its lines: a line that gives no year takes the year in the heading, unless it "
    "says otherwise."
)
# A source that words a line differently is no gap. On Loong (9 November), split runs' parts each reported that the
# line a question names is not in their filing; the lead merged three such caveats into "cannot be determined" or a
# strict count, where one agent and CrewAI used the nearest line: 3 of 9 right against 6 (docs/LIVE_TESTS.md).
WORDING_RULE = (
    " A file may name a line differently from the goal. Where no line carries the goal's name, use the line that "
    "measures the same thing, say which line you used, and answer with it: a different name is not a gap."
)
# The wording note narrowed, and the checker told the same. On Loong's 9 questions (9 November) the wording note ended
# the hedging, but the checker, not told, failed the nearest lines the writers used, and "the line that measures the
# same thing" reached too far: cash and short-term investments counted as cash and cash equivalents.
SAME_RULE = (
    " A file may name a line differently from the goal. Where no line carries the goal's name, use a line that is the "
    "same measure under another name, such as 'Net sales' for 'Revenue', say which line you used, and answer with it: "
    "a different name is not a gap. A line that adds or leaves out items is a different measure, such as 'Cash and "
    "short-term investments' for 'Cash': do not use it; say the file has no line for the goal's measure."
)
SAME_VERIFY = (
    " A product may answer with a line that is the same measure the goal names under another name, if it says which "
    "line it used: that is an answer, so do not FAIL it for the name alone. FAIL a product that uses a line that adds "
    "or leaves out items the goal's measure does not, as a different measure."
)
# A product that names its own gap is no answer. On the rerun of 5 November, 5 of the 6 wrong answers that finished had
# set a named company aside ("contributes 0", "unresolved") and were passed under the sample rule, which says a figure
# no file covers is no fault (docs/LIVE_TESTS.md).
NAMED_RULE = (
    " A product that leaves out, sets aside or counts as zero anything the goal names, whatever reason it gives, has "
    "not answered the goal: FAIL it and name what is missing."
)
# The named rule narrowed to what a product says of itself. On the gap test of 6 November the named rule caught all 37
# wrong merges but failed 22 more right ones, most of which only listed figures for some companies, or said look-alike
# names or other years' figures were kept out. All 6 wrong ones it alone caught said a named company had no figure,
# contributed 0 or was set aside.
ASIDE_RULE = (
    " A product that says something the goal names has no figure, could not be found, counts as zero or was set "
    "aside has not answered the goal: FAIL it and name what is missing. Keeping out look-alike names or other "
    "periods' figures is not this, and a product need not list every figure it used."
)
# A product's own words that it has no figure for something, adds 0 for it, or set it aside (--gap-check). Fixed on
# 7 November from the gap test's merges, before any other product was read against it, and not changed after: on 318
# merges no rule was written from, it matched 3 of the 5 wrong products the default rule passes, and 8 right ones.
GAP_SAID = re.compile(
    r"has no (?:FY20\d\d )?(?:Q[1-4] )?(?:revenue |churn )?figure|has no FY20\d\d|no (?:FY20\d\d )?Q[1-4] figure|"
    r"contribut\w* (?:0|zero|nothing|\$0)|counted (?:as|at) (?:0|zero)|amount is not included|is not included|"
    r"(?:figure|\$[\d.]+ ?M?) (?:is|was) (?:excluded|set aside|left out)|(?:set|sets) aside|not (?:retrieved|found)\b|"
    r"cannot be (?:settled|resolved|confirmed)|unresolved", re.I)
GAP_SAID_CHARS = 300


def gap_said(claim: str) -> str:
    """The sentence of the product in which it says it has no figure for something, adds 0 for it or set it aside;
    empty if none. The kernel's check, not the model's: it reads the product's own words and nothing else."""
    found = GAP_SAID.search(claim or "")
    if not found:
        return ""
    start = max(claim.rfind(". ", 0, found.start()) + 2, claim.rfind("\n", 0, found.start()) + 1, 0)
    ends = [i for i in (claim.find(". ", found.end()), claim.find("\n", found.end())) if i >= 0]
    end = min(ends) + 1 if ends else len(claim)
    return " ".join(claim[start:end].split())[:GAP_SAID_CHARS]


# What the verifier is told after the source rule unless a run names another. On five seeds no tape had used, right
# answers failed fell from 69 of 220 to 6, and wrong answers caught went from 36 of 39 to 37 (docs/LIVE_TESTS.md).
VERIFY_RULE = SAMPLE_RULE + HEADING_RULE
# What the lead and sub-agents can be told about an undated line (--author-rule). Off until a run shows it pays: on the
# held-out seeds, 23 of 33 wrong answers were an author refusing a figure its file holds, on a line with no year.
AUTHOR_RULES: dict[str, str] = {"none": "", "headed": HEADING_RULE.strip(), "wording": WORDING_RULE.strip(),
                                 "same": SAME_RULE.strip()}

_READ_HEAD = re.compile(r"\[read ([^\]\n]+)\](?:\n| already in full above)")
_MATCH_LINE = re.compile(r"^([^\[\n:][^\n:]*):\d+: ", re.MULTILINE)
_QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")
_ELLIPSIS = re.compile(r"\.{3}|…")
# Quotes of something other than a file, seen on Haiku: the tool's own words, a search query, a member's report.
TOOL_WORDS = ("not found in the workspace", "more matches not shown", "no matches")
_QUERY_BEFORE = re.compile(r"\b(?:retrieve|retrieval|query|search(?:ed)?|for)\W*$", re.IGNORECASE)
_REPORT = re.compile(r"\bchannel\b|\bsub-agent\b", re.IGNORECASE)


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


def _mentions(text: str, names: Iterable[str]) -> list[tuple[int, int, str]]:
    """Every place the text names a file by file name: (start, end, file), in order."""
    low = (text or "").lower()
    found = set()
    for name in dict.fromkeys(names):
        for form in dict.fromkeys((name.lower(), Path(name).name.lower())):
            rx = re.compile(r"(?<![\w.-])" + re.escape(form) + r"(?![\w-])")
            found.update((m.start(), m.end(), name) for m in rx.finditer(low))
    return sorted(found)


def cited_in(text: str, names: Iterable[str]) -> list[str]:
    """Files the text names by file name, such as orbrook.md, in order of mention."""
    first: dict[str, int] = {}
    for start, _, name in _mentions(text, names):
        first.setdefault(name, start)
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


_ESCAPED = re.compile(r"\\u([0-9a-fA-F]{4})")


def _norm(text: str) -> str:
    # A reply can carry a dash as the text \u2013, escaped twice; read it as the dash.
    return " ".join(_ESCAPED.sub(lambda m: chr(int(m.group(1), 16)), text).lower().split())


def misquoted(toolbox, product: Artifact, names: list[str]) -> list[str]:
    """Evidence whose quote is not in the file it cites. Checked in code, for nothing. A paraphrase is
    flagged too, so the verifier is told and judges; the kernel does not fail the product on this alone."""
    out = []
    for item in product.evidence:
        quotes = list(_QUOTED.finditer(item))
        outside = _QUOTED.sub(" ", item)
        if _REPORT.search(outside):
            continue  # its quotes may be a member's words, not a file's
        # A file named inside a quote is quoted text, not a citation.
        cites = [(end, name) for start, end, name in _mentions(item, names)
                 if not any(q.start() <= start < q.end() for q in quotes)]
        bodies = {name: _norm(text) for _, name in cites if (text := toolbox.text_of(name)) is not None}
        for q in quotes:
            if any(w in _norm(q.group(1)) for w in TOOL_WORDS) or _QUERY_BEFORE.search(item[:q.start()]):
                continue
            # A quote is flagged when no file the item cites holds it; it is named by the file before it.
            pieces = [_norm(p.strip(" .,;:")) for p in _ELLIPSIS.split(q.group(1))]
            if not bodies or any(all(p in body for p in pieces if len(p) >= MIN_QUOTE) for body in bodies.values()):
                continue
            before = [name for end, name in cites if end <= q.start() and name in bodies]
            out.append(f"{before[-1] if before else next(iter(bodies))}: {item[:160]}")
            break
    return out


def source_block(toolbox, name: str, why: str) -> str:
    return f"(picked: {why})\n{toolbox.read(name)}"
