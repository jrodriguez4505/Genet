"""Scores the head-to-head's Loong answers with Loong's own judge prompt (docs/HEAD_TO_HEAD.md).

The judge sees the question, the gold answer and one answer: never which contender gave it. The same answer
to the same question is judged once and its score shared, so the scores do not depend on the order trials ran
in. An answer that is missing scores 0 without a call. Right is a score of 100, Loong's perfect rate.
"""

from __future__ import annotations

from .benchmarks import judge_prompt, judge_score, loong_judge_question
from .rawcall import RawClient

PERFECT = 100.0
JUDGE_REPLY = 1_024  # Loong asks for no more than 100 words of evidence and a rating


def judge_rows(results: list[dict], loong_rows: list[dict], client: RawClient, model: str,
               progress=None) -> list[dict]:
    """Each Loong trial in results with its judge score. Trials of other benchmarks pass through unscored."""
    by_task = {f"loong-{r['id'][:8]}": r for r in loong_rows}
    seen: dict[tuple[str, str], tuple[float | None, str]] = {}
    out = []
    for n, res in enumerate(results, 1):
        row = by_task.get(res.get("task_id", ""))
        if row is None:
            out.append(dict(res))
            continue
        answer = (res.get("answer") or "").strip()
        pair = (res["task_id"], answer)
        if pair not in seen:
            if not answer:
                seen[pair] = (0.0, "no answer")
            else:
                prompt = judge_prompt(loong_judge_question(row), res.get("expected") or str(row["answer"]), answer)
                msg = client.messages.create(model=model, max_tokens=JUDGE_REPLY,
                                             messages=[{"role": "user", "content": prompt}])
                text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
                seen[pair] = (judge_score(text), text)
            if progress:
                progress(f"[{n}/{len(results)}] {res['task_id']} {res.get('strategy', '')}: {seen[pair][0]}")
        score, text = seen[pair]
        out.append(dict(res) | {"judge_score": score, "judge_text": text,
                                "answer_right": score == PERFECT,
                                "correct": score == PERFECT and res.get("status") == "complete"})
    return out
