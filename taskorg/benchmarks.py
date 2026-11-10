"""Public benchmarks for the head-to-head (docs/HEAD_TO_HEAD.md): Loong's English SEC filings and HotpotQA.

Each question becomes a Task with its own workspace, its own context and its own way of being scored, so the
same compare harness that runs the generated suite runs these, and a framework harness can load the same
questions. Nothing here downloads: the operator fetches the files (data/h2h/) and passes their paths.

Loong (https://github.com/MozerWang/Loong, Apache-2.0): questions over 2 to 5 financial filings each, scored by
a judge model with the benchmark's own prompt (LOONG_JUDGE). HotpotQA (https://hotpotqa.github.io/, CC BY-SA
4.0): short questions over 10 Wikipedia paragraphs, scored by exact match after the usual normalising.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from .suite import Suite, Task, slug

LOONG_SEED = 1108
LOONG_SETS = (1, 2)          # 10,000 to 100,000 tokens of filings a question, in Loong's count
LOONG_LEVELS = (1, 2, 3, 4)  # spotlight locating, comparison, clustering, chain of reasoning
LOONG_PER_LEVEL = 10
# Questions no earlier run used, for a check of a change made after reading the main sample: comparison and
# clustering, where split runs lost on line names (docs/LIVE_TESTS.md, 9 November). Drawn once, before the run.
LOONG_FRESH_SEED = 1109
LOONG_FRESH = {2: 6, 3: 6}
LEVEL_NAMES = {1: "spotlight", 2: "comparison", 3: "clustering", 4: "chain"}

LOONG_CONTEXT = (
    "The workspace holds {n} filings with the U.S. SEC, annual or quarterly reports as plain text, one file per "
    "filing, named after the company, or after the filing's year where they are one company's. Filings are long: "
    "a read returns one page and says how to ask for the next, and a search finds lines across all of them. "
    "Use the files; do not guess. The files: {files}. The question's own instruction: {instruction}"
)
LOONG_PURPOSE = "Answer from the filings only. End the product with ANSWER: <answer> on one line."
LOONG_DONE_WHEN = "The product ends with 'ANSWER: <answer>' on one line, answering every part of the question."

HOTPOT_CONTEXT = (
    "The workspace holds 10 short Wikipedia paragraphs, one file per article, named after its title. Some are about "
    "look-alike subjects and do not answer the question. Use the files; do not guess. The files: {files}."
)
HOTPOT_PURPOSE = "Answer from the paragraphs only. End the product with ANSWER: <answer>"
HOTPOT_DONE_WHEN = "The product ends with 'ANSWER: <answer>': as few words as the answer needs, or yes or no."

# Loong's judge prompt, from src/utils/prompt.py at commit 6d2115b (Apache-2.0), unchanged but for the three slots.
LOONG_JUDGE = '''[Question]
{question}

[Gold Answer]
{gold}

[The Start of Assistant's Predicted Answer]
{predicted}
[The End of Assistant's Predicted Answer]

[System]
We would like to request your feedback on the performance of the AI assistant in response to the user question displayed above according to the gold answer. Please use the following listed aspects and their descriptions as evaluation criteria:
    - Accuracy and Hallucinations: The assistant's answer is semantically consistent with the gold answer; The numerical value and order need to be accurate, and there should be no hallucinations.
    - Completeness: Referring to the reference answers, the assistant's answer should contain all the key points needed to answer the user's question; further elaboration on these key points can be omitted.
Please rate whether this answer is suitable for the question. Please note that the gold answer can be considered as a correct answer to the question.

The assistant receives an overall score on a scale of 1 to 100, where a higher score indicates better overall performance.
Please note that if the assistant's answer and the gold answer fully meet the above criteria, its overall rating should be the full marks (100).
Please first provide a comprehensive explanation of your evaluation, avoiding any potential bias.
Then, output a line indicating the score of the Assistant.

PLEASE OUTPUT WITH THE FOLLOWING FORMAT, WHERE THE SCORE IS A SCALE OF 1 TO 100 BY STRICTLY FOLLOWING THIS FORMAT: "[[score]]", FOR EXAMPLE "Rating: [[100]]":
<start output>
Evaluation evidence: your evluation explanation here, no more than 100 words
Rating: [[score]]
<end output>

Now, start your evaluation:'''

_SCORE = (re.compile(r"\[\[([0-9]*\.?[0-9]+)\]\]"), re.compile(r"\[([0-9]*\.?[0-9]+)\]"))


class BenchmarkError(ValueError):
    """A benchmark file that is not what the head-to-head was planned on."""


def read_jsonl(path: str | Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise BenchmarkError(f"{path} line {n} is not JSON: {e.msg}") from None
    return rows


# --- Loong ---

def _filing_names(docs_dir: str | Path) -> list[str]:
    return sorted(p.name for p in Path(docs_dir).iterdir() if p.suffix == ".txt")


def _matches(row: dict, doc: str, names: list[str]) -> list[str]:
    want = f"2024-{doc}" if row["level"] != 4 else doc
    return [n for n in names if want in n]


def loong_pool(rows: list[dict], level: int, docs_dir: str | Path) -> list[dict]:
    """The English financial questions of the planned sets at one level, in a fixed order. A question that names a
    company with two filings is left out: Loong takes whichever the file system lists first, so its gold answer
    may come from either."""
    names = _filing_names(docs_dir)
    pool = [r for r in rows if r.get("type") == "financial" and r.get("language") == "en"
            and r.get("set") in LOONG_SETS and r.get("level") == level
            and all(len(_matches(r, d, names)) == 1 for d in r["doc"])]
    return sorted(pool, key=lambda r: r["id"])


def loong_sample(rows: list[dict], docs_dir: str | Path, seed: int = LOONG_SEED,
                 per_level: int = LOONG_PER_LEVEL) -> dict[str, list[str]]:
    """Ids, fixed before any run: for each level, a seeded draw of per_level + 1; the first is calibration."""
    out: dict[str, list[str]] = {"calibration": [], "main": []}
    for level in LOONG_LEVELS:
        pool = loong_pool(rows, level, docs_dir)
        if len(pool) < per_level + 1:
            raise BenchmarkError(f"level {level} has {len(pool)} questions, the plan needs {per_level + 1}")
        picks = random.Random(seed * 10 + level).sample(pool, per_level + 1)
        out["calibration"].append(picks[0]["id"])
        out["main"] += [r["id"] for r in picks[1:]]
    return out


def loong_fresh(rows: list[dict], docs_dir: str | Path, seed: int = LOONG_FRESH_SEED,
                per_level: dict[int, int] | None = None) -> list[str]:
    """Ids no earlier sample holds: for each level, a seeded draw from what the main and calibration draws left."""
    planned = loong_sample(rows, docs_dir)
    used = set(planned["main"]) | set(planned["calibration"])
    out: list[str] = []
    for level, n in (per_level or LOONG_FRESH).items():
        pool = [r for r in loong_pool(rows, level, docs_dir) if r["id"] not in used]
        if len(pool) < n:
            raise BenchmarkError(f"level {level} has {len(pool)} unused questions, the fresh draw needs {n}")
        out += [r["id"] for r in random.Random(seed * 10 + level).sample(pool, n)]
    return out


def loong_files(row: dict, docs_dir: str | Path) -> list[tuple[str, Path]]:
    """Each of a question's filings: the name it gets in the workspace, and its file in Loong's doc/financial.

    Loong finds a level 1 to 3 filing as *2024-<name>*.txt and a level 4 one as *<name>*.txt; a name that finds
    none, or more than one, is an error here rather than Loong's first match."""
    docs = Path(docs_dir)
    names = _filing_names(docs)
    out, seen = [], set()
    for doc in row["doc"]:
        found = _matches(row, doc, names)
        if len(found) != 1:
            raise BenchmarkError(f"question {row['id']}: {doc!r} matches {len(found)} filings")
        shown = slug(doc)[:60] + ".txt"
        if shown in seen:
            raise BenchmarkError(f"question {row['id']}: two filings would share the name {shown}")
        seen.add(shown)
        out.append((shown, docs / found[0]))
    return out


def loong_task(row: dict, docs_dir: str | Path) -> tuple[Task, dict[str, str]]:
    files = loong_files(row, docs_dir)
    ws = f"loong-{row['id'][:8]}"
    task = Task(
        id=ws, family=f"loong-{LEVEL_NAMES[row['level']]}", question=row["question"].strip(),
        answer=row["answer"] if isinstance(row["answer"], str) else json.dumps(row["answer"], ensure_ascii=False),
        kind="judge", workspace=ws,
        context=LOONG_CONTEXT.format(n=len(files), files=", ".join(name for name, _ in files),
                                     instruction=row["instruction"].strip()),
        purpose=LOONG_PURPOSE, done_when=LOONG_DONE_WHEN,
    )
    corpus = {f"{ws}/{name}": path.read_text(encoding="utf-8", errors="replace") for name, path in files}
    return task, corpus


def loong_suite(questions: str | Path, docs_dir: str | Path, which: str = "main", ids: list[str] | None = None) -> Suite:
    rows = read_jsonl(questions)
    by_id = {r["id"]: r for r in rows}
    if ids is not None:
        wanted = ids
    elif which == "fresh":
        wanted = loong_fresh(rows, docs_dir)
    else:
        wanted = loong_sample(rows, docs_dir)[which]
    tasks, corpus = [], {}
    for qid in wanted:
        if qid not in by_id:
            raise BenchmarkError(f"no Loong question {qid}")
        task, files = loong_task(by_id[qid], docs_dir)
        tasks.append(task)
        corpus.update(files)
    return Suite(seed=LOONG_SEED, companies={}, corpus=corpus, tasks=tasks)


def loong_judge_question(row: dict) -> str:
    """The question as Loong's judge sees it: the prompt template with the documents left out."""
    return (row["prompt_template"].replace("{docs}", "").replace("{question}", row["question"])
            .replace("{instruction}", row["instruction"]))


def judge_prompt(question: str, gold: str, predicted: str) -> str:
    return LOONG_JUDGE.format(question=question, gold=gold, predicted=predicted)


def judge_score(text: str) -> float | None:
    """The score in a judge's reply, read as Loong reads it: [[n]], else [n]."""
    for pattern in _SCORE:
        m = pattern.search(text or "")
        if m:
            return float(m.group(1))
    return None


# --- HotpotQA ---

def hotpot_task(row: dict) -> tuple[Task, dict[str, str]]:
    ws = f"hotpot-{row['id'][:8]}"
    corpus, seen = {}, set()
    for title, sentences in zip(row["context"]["title"], row["context"]["sentences"]):
        name = slug(title)[:60] or "untitled"
        while name in seen:
            name += "-2"
        seen.add(name)
        corpus[f"{ws}/{name}.txt"] = f"{title}\n" + "".join(sentences).strip() + "\n"
    names = ", ".join(n.split("/", 1)[1] for n in corpus)
    task = Task(id=ws, family=f"hotpot-{row['type']}", question=row["question"].strip(), answer=row["answer"],
                kind="text", workspace=ws, context=HOTPOT_CONTEXT.format(files=names), purpose=HOTPOT_PURPOSE,
                done_when=HOTPOT_DONE_WHEN)
    return task, corpus


def hotpot_suite(questions: str | Path) -> Suite:
    tasks, corpus = [], {}
    for row in read_jsonl(questions):
        task, files = hotpot_task(row)
        tasks.append(task)
        corpus.update(files)
    return Suite(seed=LOONG_SEED, companies={}, corpus=corpus, tasks=tasks)
