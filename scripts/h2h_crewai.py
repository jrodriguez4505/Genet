"""CrewAI on the head-to-head's questions (docs/HEAD_TO_HEAD.md), every call through Genet's RawClient.

CrewAI runs its hierarchical process: a manager that delegates to 4 reader agents, each with the same three
read-only tools Genet's agents have (read a file a page at a time, search, list), over the same files. Its own
Anthropic provider builds every request, with native tool calls; only the client underneath is Genet's, so
CrewAI's calls are sized, capped, counted, priced and taped exactly as Genet's are. Results come out in compare's
format, strategy "crewai", so the judge and the readers take them as they take Genet's.

Run it with the CrewAI environment's Python and the project on the path (the key from TASKORG_ANTHROPIC_KEY only):
  PYTHONPATH=. data/h2h/venv-crewai/bin/python scripts/h2h_crewai.py --benchmark hotpot \\
      --questions data/h2h/hotpotqa/questions.jsonl --record data/tapes/T.jsonl --out data/compare/R.json ...
"""

from __future__ import annotations

import os

# Before CrewAI is imported: no telemetry, no tracing, and no provider key or model for a call that would go round
# Genet's client to find.
for _k, _v in {"CREWAI_DISABLE_TELEMETRY": "true", "OTEL_SDK_DISABLED": "true", "CREWAI_DISABLE_TRACKING": "true",
               "CREWAI_TRACING_ENABLED": "false"}.items():
    os.environ[_k] = _v
for _k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "MODEL", "OPENAI_MODEL_NAME", "OPENAI_API_BASE"):
    os.environ.pop(_k, None)

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

from crewai import Agent, Crew, Process  # noqa: E402
from crewai import Task as CrewTask  # noqa: E402
from crewai.llms.context_window import CONTEXT_WINDOW_USAGE_RATIO  # noqa: E402
from crewai.llms.providers.anthropic.completion import AnthropicCompletion  # noqa: E402
from crewai.tools import BaseTool  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from taskorg.benchmarks import hotpot_suite, loong_suite  # noqa: E402
from taskorg.compare import TrialResult, render, save, summarize  # noqa: E402
from taskorg.errors import InvariantError  # noqa: E402
from taskorg.rawcall import RawClient, RawPlayer, RawTape, Spend, current_agent  # noqa: E402
from taskorg.suite import extract_answer, grade  # noqa: E402
from taskorg.tools import Toolbox  # noqa: E402

READERS = 4  # Genet's cap on sub-agents
READER_GOAL = ("Read the files you are asked about and report exactly what the question needs, with each figure or "
               "fact as the file states it and the file it comes from.")
READER_STORY = "You read company filings and reference articles closely, and you never guess."

# The one client every call of a run goes through, and the toolbox of the trial in progress.
_RAW: RawClient | None = None
_BOX: Toolbox | None = None


class _AsyncRaw:
    """CrewAI summarises with async calls; they go through the same client, on a thread."""

    class _M:
        async def create(self, **params):
            return await asyncio.to_thread(_RAW.create, **params)

        async def count_tokens(self, **params):
            return _RAW.messages.count_tokens(**params)

    def __init__(self):
        self.messages = self._M()
        self.beta = self


class GenetLLM(AnthropicCompletion):
    """CrewAI's own Anthropic provider, with Genet's counted, capped and taped client in place of the SDK's."""

    call_limit: int = Field(default=100_000, exclude=True)

    def _build_sync_client(self):
        return _RAW

    def _build_async_client(self):
        return _AsyncRaw()

    # Asked for on every call, never kept: the client is the run's, whatever this LLM was built with.
    def _get_sync_client(self):
        return _RAW

    def _get_async_client(self):
        return _AsyncRaw()

    def get_context_window_size(self) -> int:
        # CrewAI's own convention: the usable part of the window, after its reserve.
        return int(self.call_limit * CONTEXT_WINDOW_USAGE_RATIO)

    def call(self, messages, tools=None, callbacks=None, available_functions=None, from_task=None, from_agent=None,
             response_model=None, **kwargs):
        token = current_agent.set(getattr(from_agent, "role", "") or "")
        try:
            return super().call(messages, tools=tools, callbacks=callbacks, available_functions=available_functions,
                                from_task=from_task, from_agent=from_agent, response_model=response_model, **kwargs)
        finally:
            current_agent.reset(token)


class _ReadArgs(BaseModel):
    path: str = Field(description="the file's name as listed")
    page: int = Field(default=1, description="the page to read; long files have more than one")


class _SearchArgs(BaseModel):
    query: str = Field(description="words to find; lines with all of them come back first")


class _ListArgs(BaseModel):
    folder: str = Field(default="", description="leave empty for the whole workspace")


class ReadFile(BaseTool):
    name: str = "read_file"
    description: str = "Read a workspace file. A long file comes a page at a time; the result says how many pages it has."
    args_schema: type[BaseModel] = _ReadArgs

    def _run(self, path: str, page: int = 1) -> str:
        return _BOX.run(f"read:{path}@{page}" if page and page > 1 else f"read:{path}")


class SearchFiles(BaseTool):
    name: str = "search_files"
    description: str = "Search every workspace file for lines with these words."
    args_schema: type[BaseModel] = _SearchArgs

    def _run(self, query: str) -> str:
        return _BOX.run(f"retrieve:{query}")


class ListFiles(BaseTool):
    name: str = "list_files"
    description: str = "List the workspace's files."
    args_schema: type[BaseModel] = _ListArgs

    def _run(self, folder: str = "") -> str:
        return _BOX.run(f"observe:{folder}" if folder else "observe")


def crew_for(task, llm) -> Crew:
    readers = [Agent(role=f"Reader {i}", goal=READER_GOAL, backstory=READER_STORY, llm=llm,
                     tools=[ReadFile(), SearchFiles(), ListFiles()], allow_delegation=False, max_retry_limit=0,
                     cache=False, verbose=False) for i in range(1, READERS + 1)]
    job = CrewTask(description=f"{task.question}\n\n{task.context}\n\n{task.purpose}", expected_output=task.done_when)
    return Crew(agents=readers, tasks=[job], process=Process.hierarchical, manager_llm=llm, memory=False,
                planning=False, cache=False, verbose=False, share_crew=False, tracing=False)


def run_trial(task, root: Path, llm, args) -> TrialResult:
    global _BOX
    _BOX = Toolbox(roots=[root / task.workspace], page_chars=args.page_chars)
    _RAW.begin_trial(args.max_calls, args.max_calls * args.call_limit, args.max_seconds)
    status, code, final = "complete", "", ""
    started = time.perf_counter()
    try:
        final = str(crew_for(task, llm).kickoff().raw or "")
    except InvariantError as e:
        status, code = "abort", e.code
    except Exception as e:  # CrewAI wraps what it catches; a stop the client raised is still named in it
        status, code = "abort", "BUDGET" if "BUDGET:" in str(e) else "LIVE" if "LIVE:" in str(e) else "CRASH"
    latency = time.perf_counter() - started
    stats = _RAW.end_trial()
    if stats["stopped"] and status == "complete":
        status, code = "abort", "BUDGET"  # a reader stopped by the budget, whose manager answered anyway
    calls = [c for c in stats["calls"] if not c.get("pending")]
    answer = extract_answer(final)
    right = grade(answer, task)
    prompt = sum(c.get("prompt_tokens") or 0 for c in calls)
    completion = sum(c.get("completion_tokens") or 0 for c in calls)
    by_model: dict = {}
    for c in calls:
        row = by_model.setdefault(c.get("model") or args.model, [0, 0, 0, 0])
        for i, k in enumerate(("prompt_tokens", "completion_tokens", "cache_write_tokens", "cache_read_tokens")):
            row[i] += int(c.get(k) or 0)
    readers = {c.get("agent") for c in calls if str(c.get("agent", "")).startswith("Reader")}
    res = TrialResult(task_id=task.id, family=task.family, strategy="crewai", repeat=0, expected=task.answer,
                      answer=answer, correct=right and status == "complete", answer_right=right, status=status,
                      code=code, calls=len(calls), tokens=prompt + completion, prompt_tokens=prompt,
                      completion_tokens=completion, tokens_estimated=False, latency_s=round(latency, 3),
                      workers=len(readers), by_model=by_model)
    res.final_tail = final[-600:] if answer is None else ""  # for the record: an answer with no ANSWER: line
    return res


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--benchmark", required=True, choices=["loong", "hotpot"])
    p.add_argument("--questions", required=True)
    p.add_argument("--docs", default=None)
    p.add_argument("--which", default="main", choices=["main", "calibration"])
    p.add_argument("--model", default=os.environ.get("TASKORG_MODEL_NAME", "claude-haiku-5-5"))
    p.add_argument("--effort", default=os.environ.get("TASKORG_MODEL_EFFORT", "low") or None)
    p.add_argument("--call-limit", type=int, default=100_000)
    p.add_argument("--max-calls", type=int, default=80)
    p.add_argument("--max-seconds", type=float, default=1200.0)
    p.add_argument("--page-chars", type=int, default=16_000)
    p.add_argument("--price-in", type=float, default=None)
    p.add_argument("--price-out", type=float, default=None)
    p.add_argument("--max-spend", type=float, default=None)
    p.add_argument("--record", default=None)
    p.add_argument("--replay", default=None)
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    if args.max_spend is not None and args.price_in is None:
        p.error("--max-spend needs --price-in and --price-out")
    if bool(args.record) == bool(args.replay):
        p.error("give --record (live) or --replay")

    global _RAW
    suite = (loong_suite(args.questions, args.docs, args.which) if args.benchmark == "loong"
             else hotpot_suite(args.questions))
    spend = Spend(default=(args.price_in or 0.0, args.price_out or 0.0))
    config = {"strategies": ["crewai"], "benchmark": args.benchmark, "which": args.which, "model": args.model,
              "effort": args.effort, "context_tokens": args.call_limit, "max_calls_per_trial": args.max_calls,
              "max_seconds": args.max_seconds, "page_chars": args.page_chars, "readers": READERS,
              "crewai": __import__("crewai").__version__, "task_ids": [t.id for t in suite.tasks]}
    if args.replay:
        _RAW = RawClient(call_limit=args.call_limit, player=RawPlayer(args.replay), spend=spend, effort=args.effort)
        config["tape"] = args.replay
    else:
        tape = RawTape(args.record, {"adapter": "anthropic-raw", "purpose": "h2h-crewai"} | config)
        _RAW = RawClient.live(call_limit=args.call_limit, tape=tape, spend=spend, max_spend=args.max_spend, effort=args.effort)
        config["tape"] = args.record
    if args.price_in is not None:
        config |= {"price_in": args.price_in, "price_out": args.price_out}
    llm = GenetLLM(model=args.model, api_key="held-by-genet", call_limit=args.call_limit)

    results: list[TrialResult] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = suite.write_corpus(Path(tmp) / "corpus")
        try:
            for n, task in enumerate(suite.tasks, 1):
                if args.max_spend is not None and spend.dollars >= args.max_spend:
                    print(f"stopped after {len(results)} trials: the ${args.max_spend:.2f} cap is reached", file=sys.stderr)
                    break
                r = run_trial(task, root, llm, args)
                results.append(r)
                mark = "ok " if r.correct else ("~  " if r.answer_right else "x  ")
                print(f"[{n}/{len(suite.tasks)}] {mark}crewai {task.id:<16} {r.calls:>2} calls {r.tokens / 1000:>6.1f}k tok "
                      f"{r.latency_s:>6.1f}s w={r.workers} {r.status}{(' ' + r.code) if r.code else ''}", file=sys.stderr)
        except KeyboardInterrupt:
            print(f"interrupted after {len(results)} trials", file=sys.stderr)
        finally:
            if _RAW.tape:
                _RAW.tape.close()
    if len(results) < len(suite.tasks):
        config["stopped_after"] = len(results)
    summary = summarize(results, price_in=args.price_in, price_out=args.price_out)
    save(Path(args.out), config=config, results=results, summary=summary)
    # The answers with no ANSWER: line, kept beside the results for reading.
    tails = {r.task_id: r.final_tail for r in results if getattr(r, "final_tail", "")}
    if tails:
        Path(args.out).with_suffix(".unmarked.json").write_text(json.dumps(tails, indent=2, ensure_ascii=False))
    print(render(summary))
    if args.replay:
        print(f"replay: {_RAW.player.served} replies served, {_RAW.player.misses} requests the tape does not have")
    else:
        print(f"tape: {_RAW.tape.count} exchanges saved to {args.record}; ${spend.dollars:.4f} by its prices")
    print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
