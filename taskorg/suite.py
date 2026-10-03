"""A synthetic, seeded task suite for comparing task-organization strategies.

The corpus is one operating-notes file per company. Facts are written in varied
prose ("third-quarter sales came in at ...", "Q3 revenue: ..."), so a single
search cannot shortcut the reading. Each file also carries distractors: last
year's figures and look-alike sister companies. Ground truth is exact and only
stated once, in the company's own file.

Families, and what each one stresses:

  lookup     one company, one figure            one source is the whole picture
  aggregate  sum of one figure over 3 companies independent parts, arithmetic
  compare    look-alike pair, higher churn      interference between similar names
  breadth    max of one figure over 5 companies many sources, context pressure
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from pathlib import Path

FAMILIES = ("lookup", "aggregate", "compare", "breadth")

# Look-alike pairs share a stem. Ground truth never crosses between them.
PAIRS = [
    ("Halvorsen Freight", "Halvorsen Freight Labs"),
    ("Quillon Bio", "Quillon Biologics"),
    ("Kestrel Mills", "Kestrel Mill Supply"),
    ("Saffron Grid", "Saffron Grid Partners"),
]
SINGLES = ["Marrowgate", "Tessaline", "Orbrook", "Vantaro", "Pellucid Air", "Corvane"]
COMPANIES = [name for pair in PAIRS for name in pair] + SINGLES

QUARTER_WORDS = {
    "Q1": ("the first quarter", "Q1", "the January–March quarter"),
    "Q2": ("the second quarter", "Q2", "the April–June quarter"),
    "Q3": ("the third quarter", "Q3", "the July–September quarter"),
    "Q4": ("the fourth quarter", "Q4", "the October–December quarter"),
}
REVENUE = (
    "Revenue for {q} reached ${v} million.",
    "{Q} revenue came in at ${v}M.",
    "The company booked ${v} million in revenue during {q}.",
    "Sales in {q} totaled ${v} million.",
)
CHURN = (
    "Customer churn in {q} was {v}%.",
    "{Q} churn ran at {v} percent.",
    "The churn rate for {q} settled at {v}%.",
)
FILLER = (
    "Warehouse utilization averaged {a}% across the network.",
    "Headcount ended the period at {n}, with most hiring in operations.",
    "Gross margin held near {a}% despite input costs.",
    "Management expects procurement savings of roughly {a} basis points.",
    "The board approved a capital plan of ${m} million for new equipment.",
    "On-time delivery improved to {a}% after the routing change.",
    "Support tickets fell by {a}% quarter over quarter.",
    "The company opened {k} new regional offices during the year.",
)
REGIONS = ("Northeast", "Midwest", "Pacific", "Gulf Coast", "Mountain West", "Mid-Atlantic")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@dataclass
class Company:
    name: str
    region: str
    revenue: dict[str, float]  # FY2026, $M by quarter
    churn: dict[str, float]    # FY2026, % by quarter
    revenue_fy2025_q3: float   # distractor
    sister: str = ""


@dataclass
class Task:
    id: str
    family: str
    question: str
    answer: str
    kind: str  # "number" | "name"
    entities: list[str] = field(default_factory=list)


@dataclass
class Suite:
    seed: int
    companies: dict[str, Company]
    corpus: dict[str, str]  # file name -> text
    tasks: list[Task]

    def write_corpus(self, root: str | Path) -> Path:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        for name, text in self.corpus.items():
            (root / name).write_text(text, encoding="utf-8")
        return root


def _company(rng: random.Random, name: str) -> Company:
    base = rng.uniform(20, 90)
    revenue = {q: round(base * rng.uniform(0.9, 1.1), 1) for q in QUARTER_WORDS}
    churn = {q: round(rng.uniform(0.8, 6.5), 1) for q in QUARTER_WORDS}
    return Company(name, rng.choice(REGIONS), revenue, churn, round(base * rng.uniform(0.75, 0.95), 1))


def _doc(rng: random.Random, c: Company, sister: Company | None) -> str:
    sentences = []
    for q, words in QUARTER_WORDS.items():
        sentences.append(rng.choice(REVENUE).format(q=rng.choice(words), Q=q, v=f"{c.revenue[q]:.1f}"))
        sentences.append(rng.choice(CHURN).format(q=rng.choice(words), Q=q, v=f"{c.churn[q]:.1f}"))
    sentences.append(f"In FY2025, third-quarter revenue had been ${c.revenue_fy2025_q3:.1f} million.")
    for _ in range(rng.randint(14, 22)):
        sentences.append(rng.choice(FILLER).format(
            a=rng.randint(3, 97), n=rng.randint(80, 900), m=round(rng.uniform(2, 40), 1), k=rng.randint(1, 6)))
    if sister:
        sentences.append(
            f"{sister.name} is a separate company and reports its own figures; "
            f"its FY2025 third-quarter revenue was ${sister.revenue_fy2025_q3:.1f} million."
        )
    rng.shuffle(sentences)
    paragraphs = [" ".join(sentences[i : i + 4]) for i in range(0, len(sentences), 4)]
    return f"# {c.name}: FY2026 operating notes\n\nRegion: {c.region}.\n\n" + "\n\n".join(paragraphs) + "\n"


def _names(items: list[str]) -> str:
    return ", ".join(items[:-1]) + f" and {items[-1]}" if len(items) > 1 else items[0]


def build_suite(seed: int = 7, per_family: int = 5, families: tuple[str, ...] = FAMILIES) -> Suite:
    rng = random.Random(seed)
    companies = {name: _company(rng, name) for name in COMPANIES}
    for a, b in PAIRS:
        companies[a].sister, companies[b].sister = b, a
    corpus = {
        f"{slug(c.name)}.md": _doc(rng, c, companies.get(c.sister)) for c in companies.values()
    }
    quarters = list(QUARTER_WORDS)
    tasks: list[Task] = []
    for family in families:
        made = 0
        while made < per_family:
            q = rng.choice(quarters)
            if family == "lookup":
                c = companies[rng.choice(COMPANIES)]
                if rng.random() < 0.5:
                    question = f"What was {c.name}'s FY2026 {q} revenue, in $ millions?"
                    answer, kind = f"{c.revenue[q]:.1f}", "number"
                else:
                    question = f"What was {c.name}'s FY2026 {q} customer churn, in percent?"
                    answer, kind = f"{c.churn[q]:.1f}", "number"
                entities = [c.name]
            elif family == "aggregate":
                entities = rng.sample(COMPANIES, 3)
                total = sum(companies[n].revenue[q] for n in entities)
                question = f"What was the combined FY2026 {q} revenue, in $ millions, of {_names(entities)}?"
                answer, kind = f"{total:.1f}", "number"
            elif family == "compare":
                a, b = rng.choice(PAIRS)
                if abs(companies[a].churn[q] - companies[b].churn[q]) < 0.3:
                    continue
                entities = [a, b] if rng.random() < 0.5 else [b, a]
                question = f"Which had the higher FY2026 {q} customer churn: {entities[0]} or {entities[1]}?"
                answer, kind = max(entities, key=lambda n: companies[n].churn[q]), "name"
            elif family == "breadth":
                entities = rng.sample(COMPANIES, 5)
                ranked = sorted(entities, key=lambda n: companies[n].revenue[q], reverse=True)
                if companies[ranked[0]].revenue[q] - companies[ranked[1]].revenue[q] < 0.5:
                    continue
                question = f"Of {_names(entities)}, which had the highest FY2026 {q} revenue?"
                answer, kind = ranked[0], "name"
            else:
                raise ValueError(f"unknown family: {family}")
            made += 1
            tasks.append(Task(f"{family}-{made}", family, question, answer, kind, entities))
    return Suite(seed, companies, corpus, tasks)


# --- grading ---

_ANSWER = re.compile(r"ANSWER:\s*(.+)", re.IGNORECASE)
_NUMBER = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")


def extract_answer(text: str) -> str | None:
    """The last 'ANSWER: <value>' line in a product."""
    found = _ANSWER.findall(text or "")
    return found[-1].strip() if found else None


def _norm_name(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9& ]+", " ", text.lower())).strip()


def grade(answer: str | None, task: Task) -> bool:
    if not answer:
        return False
    if task.kind == "number":
        m = _NUMBER.search(answer.replace("$", ""))
        return bool(m) and abs(float(m.group().replace(",", "")) - float(task.answer)) <= 0.05 + 1e-9
    got = _norm_name(answer)
    return got in (_norm_name(task.answer), slug(task.answer).replace("-", " "))
