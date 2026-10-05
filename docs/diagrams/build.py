"""Render Genet's explainer diagrams.

    python docs/diagrams/build.py

Writes docs/img/<name>-light.svg and -dark.svg for the README (GitHub swaps them
with <picture>), and rewrites the inline copies in docs/index.html between
<!-- figure:<name> --> markers, where they take the page's text color.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMG = ROOT / "docs" / "img"
SITE = ROOT / "docs" / "index.html"
FONT = "ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

# (color, opacity). "inline" inherits the page's text color.
THEMES = {
    "light": {
        "ink": ("#1f2328", 1), "muted": ("#59636e", 1), "line": ("#8c959f", 1), "faint": ("#d0d7de", 1),
        "accent": ("#bc4c00", 1), "accent_fill": ("#fff1e5", 1), "fill": ("#f6f8fa", 1),
    },
    "dark": {
        "ink": ("#e6edf3", 1), "muted": ("#9198a1", 1), "line": ("#6e7681", 1), "faint": ("#3d444d", 1),
        "accent": ("#f0883e", 1), "accent_fill": ("#3a2214", 1), "fill": ("#161b22", 1),
    },
    "inline": {
        "ink": ("currentColor", 1), "muted": ("currentColor", 0.68), "line": ("currentColor", 0.5),
        "faint": ("currentColor", 0.22), "accent": ("#e0743a", 1), "accent_fill": ("#e0743a", 0.14),
        "fill": ("currentColor", 0.05),
    },
}


class Canvas:
    def __init__(self, name: str, w: int, h: int, theme: str, claim: str):
        self.name, self.w, self.h, self.t, self.claim = name, w, h, THEMES[theme], claim
        self.parts: list[str] = []
        self.markers: set[str] = set()

    def paint(self, attr: str, key: str) -> str:
        color, opacity = self.t[key]
        return f'{attr}="{color}"' + (f' {attr}-opacity="{opacity}"' if opacity != 1 else "")

    def text(self, x, y, s, *, size=13, color="ink", anchor="middle", weight=400):
        self.parts.append(
            f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
            f'{self.paint("fill", color)}>{escape(s)}</text>'
        )

    def rect(self, x, y, w, h, *, stroke="line", fill=None, dash=False, rx=8, sw=1.5):
        fill_attr = self.paint("fill", fill) if fill else 'fill="none"'
        dash_attr = ' stroke-dasharray="5 4"' if dash else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" {fill_attr} '
            f'{self.paint("stroke", stroke)} stroke-width="{sw}"{dash_attr}/>'
        )

    def box(self, x, y, w, h, title, sub=None, *, accent=False, dash=False):
        self.rect(x, y, w, h, stroke="accent" if accent else "line", fill="accent_fill" if accent else "fill", dash=dash)
        cx, cy = x + w / 2, y + h / 2
        if sub:
            self.text(cx, cy - 3, title, weight=600, color="accent" if accent else "ink")
            self.text(cx, cy + 13, sub, size=11, color="muted")
        else:
            self.text(cx, cy + 4.5, title, weight=600, color="accent" if accent else "ink")

    def arrow(self, d: str, *, color="ink", dash=False, head=True):
        mid = f"{self.name}-head-{color}"
        if head:
            self.markers.add(color)
        dash_attr = ' stroke-dasharray="5 4"' if dash else ""
        end = f' marker-end="url(#{mid})"' if head else ""
        self.parts.append(f'<path d="{d}" fill="none" {self.paint("stroke", color)} stroke-width="1.5"{dash_attr}{end}/>')

    def cross(self, x, y, r=7):
        for d in (f"M{x - r},{y - r} L{x + r},{y + r}", f"M{x - r},{y + r} L{x + r},{y - r}"):
            self.parts.append(f'<path d="{d}" {self.paint("stroke", "accent")} stroke-width="2.5" stroke-linecap="round"/>')

    def line(self, x1, y1, x2, y2, *, color="faint", sw=1):
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" {self.paint("stroke", color)} stroke-width="{sw}"/>')

    def svg(self) -> str:
        defs = "".join(
            f'<marker id="{self.name}-head-{c}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" {self.paint("fill", c)}/></marker>'
            for c in sorted(self.markers)
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" role="img" '
            f'aria-label="{escape(self.claim)}" font-family="{FONT}">'
            f"<title>{escape(self.claim)}</title><defs>{defs}</defs>{''.join(self.parts)}</svg>"
        )


# --- 1. three ways to staff the same task ---

PATTERNS = (
    "Three ways to staff the same task. A single agent uses one context. An always-split crew pays for a "
    "planner, workers and a merge on every task. Genet's lead proposes sub-tasks and policy gates decide "
    "whether a fan-out happens at all; otherwise the lead works alone."
)


def patterns(theme: str) -> str:
    c = Canvas("patterns", 960, 490, theme, PATTERNS)
    rows = [(75, "Single agent", ["one context"]),
            (225, "Always-split crew", ["every task fans out"]),
            (395, "Genet", ["fans out only when", "the gates approve"])]
    for y in (150, 305):
        c.line(20, y, 940, y)
    for cy, title, sub in rows:
        c.text(24, cy - 6, title, size=15, weight=700, anchor="start")
        for i, s in enumerate(sub):
            c.text(24, cy + 13 + i * 15, s, size=12, color="muted", anchor="start")
        c.box(200, cy - 15, 64, 30, "Task")
        c.box(880, cy - 15, 64, 30, "Answer")

    # single agent
    cy = 75
    c.box(310, cy - 22, 200, 44, "Agent", "reads, reasons, answers")
    c.arrow(f"M264,{cy} H310")
    c.arrow(f"M510,{cy} H880")
    c.text(695, cy - 8, "1 context holds everything", size=11, color="muted")

    # always-split crew
    cy = 225
    c.box(310, cy - 22, 120, 44, "Planner", "always splits")
    c.arrow(f"M264,{cy} H310")
    for wy in (cy - 48, cy, cy + 48):
        c.box(490, wy - 15, 120, 30, "Worker")
        c.arrow(f"M430,{cy} H460 V{wy} H490")
        c.arrow(f"M610,{wy} H640 V{cy} H670")
    c.box(670, cy - 22, 110, 44, "Merge")
    c.arrow(f"M780,{cy} H880")

    # genet
    cy, up, low = 395, 350, 450
    c.box(310, cy - 22, 120, 44, "Lead", "proposes sub-tasks")
    c.box(470, cy - 22, 110, 44, "Policy gates", "3 checks", accent=True)
    c.arrow(f"M264,{cy} H310")
    c.arrow(f"M430,{cy} H470")
    c.rect(613, up - 40, 124, 80, stroke="faint", dash=True)
    c.text(675, up + 54, "isolated contexts", size=11, color="muted")
    for sy in (up - 20, up + 20):
        c.box(625, sy - 14, 100, 28, "Sub-agent")
        c.arrow(f"M725,{sy} H742 V{up} H760")
    c.arrow(f"M580,{cy} H600 V{up - 20} H625", color="accent")
    c.arrow(f"M600,{up - 20} V{up + 20} H625", color="accent")
    c.text(595, up - 32, "2+ approved", size=11, color="accent", anchor="end", weight=600)
    c.box(760, up - 22, 90, 44, "Lead", "merges")
    c.arrow(f"M850,{up} H865 V{cy - 6} H880")
    c.arrow(f"M580,{cy} H600 V{low} H625")
    c.text(595, low + 22, "otherwise", size=11, color="muted", anchor="end")
    c.box(625, low - 17, 225, 34, "Lead works alone")
    c.arrow(f"M850,{low} H865 V{cy + 6} H880")
    return c.svg()


# --- 2. the gate funnel ---

GATES = (
    "Five proposed sub-tasks pass three gates in order. Two are refused at gate one because the work is "
    "already covered, one at gate two because it names no failure and goes back to the lead. Two clear "
    "all three gates and run as parallel sub-agents; a fan-out needs at least two."
)


def gates(theme: str) -> str:
    c = Canvas("gates", 960, 330, theme, GATES)
    rows = [92 + i * 48 for i in range(5)]
    names = ["note-a", "note-b", "note-c", "summary", "verify"]
    g = [270, 480, 690]
    c.text(110, 32, "Lead proposes", weight=700)
    c.text(110, 50, "5 sub-tasks", size=11, color="muted")
    # row lines: where each proposal ends
    ends = {0: None, 1: None, 2: 1, 3: 0, 4: 0}
    reasons = {2: "names no failure: back to the lead", 3: "summary.md already exists", 4: "verification is the verifier's job"}
    for i, y in enumerate(rows):
        c.box(40, y - 15, 140, 30, names[i])
        stop = ends[i]
        if stop is None:
            c.arrow(f"M180,{y} H770", color="accent")
        else:
            c.arrow(f"M180,{y} H{g[stop] - 4}", color="line", head=False)
            c.cross(g[stop] + 20, y)
            c.text(g[stop] + 36, y + 4, reasons[i], size=12, color="muted", anchor="start")
    spans = [(0, 4), (0, 2), (0, 1)]
    labels = ["1 · Can someone else?", "2 · Should we?", "3 · Could we?"]
    checks = ["covered · staffed · repeat · verifier", "named failure · measured need", "tier · budget · cap · skill"]
    for x, (a, b), label, check in zip(g, spans, labels, checks):
        top, bottom = rows[a] - 20, rows[b] + 20
        c.rect(x - 6, top, 12, bottom - top, stroke="accent", fill="accent", rx=4, sw=1)
        c.text(x, 32, label, weight=700, color="accent")
        c.text(x, 50, check, size=11, color="muted")
    c.box(770, rows[0] - 15, 170, rows[1] - rows[0] + 30, "2 legal", "parallel sub-agents", accent=True)
    c.text(855, rows[1] + 36, "a fan-out needs two or more", size=11, color="muted")
    return c.svg()


# --- 3. who decides what ---

CONTROL = (
    "Models only return JSON. Every change to the team, the tools or the budget is decided by code in the "
    "control plane and logged. There is no path from a model to the roster except through the schema "
    "check and the policy gates."
)


def control(theme: str) -> str:
    c = Canvas("control", 960, 460, theme, CONTROL)
    c.rect(20, 20, 920, 120, stroke="faint", dash=True, rx=12)
    c.text(36, 42, "MODEL PLANE  ·  any LLM  ·  output is untrusted", size=12, color="muted", anchor="start", weight=600)
    c.rect(20, 175, 920, 265, stroke="faint", rx=12)
    c.text(36, 197, "CONTROL PLANE  ·  Genet kernel  ·  code", size=12, color="muted", anchor="start", weight=600)

    c.box(110, 60, 180, 56, "Lead model", "orchestrator")
    c.box(640, 60, 240, 56, "Sub-agent models", "one per approved sub-task")

    c.box(110, 215, 180, 52, "Schema check", "JSON only; extra keys refused")
    c.box(350, 215, 180, 52, "Policy gates", "3 checks, in order", accent=True)
    c.box(590, 215, 150, 52, "Roster", "written only here")
    c.box(790, 215, 130, 52, "Tool allowlist", "per skill")
    c.box(790, 300, 130, 52, "Sandbox", "read-only workspace")

    c.arrow("M200,116 V215")
    c.text(210, 165, "JSON artifact", size=11, color="muted", anchor="start")
    c.arrow("M290,241 H350")
    c.text(320, 233, "proposals", size=11, color="muted")
    c.arrow("M530,241 H590", color="accent")
    c.text(560, 233, "approved", size=11, color="accent", weight=600)
    c.arrow("M680,215 V116")
    c.text(672, 165, "starts, isolated brief", size=11, color="muted", anchor="end")
    c.arrow("M850,116 V215")
    c.text(858, 165, "tool requests", size=11, color="muted", anchor="start")
    c.arrow("M855,267 V300")
    c.arrow("M790,326 H765 V116")
    c.text(757, 300, "results", size=11, color="muted", anchor="end")

    # the path that does not exist
    c.arrow("M290,100 L596,213", color="accent", dash=True)
    c.cross(440, 163)
    c.text(470, 152, "no direct write", size=11, color="accent", anchor="start", weight=600)

    c.rect(40, 372, 880, 26, stroke="faint", fill="fill", rx=6, sw=1)
    c.text(56, 389, "Budget meter: every call counts calls, tokens and seconds; the run halts at the cap", size=12, anchor="start")
    c.rect(40, 404, 880, 26, stroke="faint", fill="fill", rx=6, sw=1)
    c.text(56, 421, "Audit log: every gate record, tool call, verdict and halt", size=12, anchor="start")
    return c.svg()


FIGURES = {"patterns": patterns, "gates": gates, "control": control}


def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    for name, draw in FIGURES.items():
        for theme in ("light", "dark"):
            (IMG / f"{name}-{theme}.svg").write_text(draw(theme) + "\n", encoding="utf-8")
    if SITE.exists():
        page = SITE.read_text(encoding="utf-8")
        for name, draw in FIGURES.items():
            page = re.sub(
                rf"(<!-- figure:{name} -->).*?(<!-- /figure:{name} -->)",
                lambda m, svg=draw("inline"): m.group(1) + svg + m.group(2),
                page,
                flags=re.S,
            )
        SITE.write_text(page, encoding="utf-8")
    print(f"wrote {len(FIGURES) * 2} SVGs to {IMG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
