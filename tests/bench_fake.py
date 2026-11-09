"""A stand-in reader for the head-to-head's public questions, to rehearse the plumbing at $0.

The simulated reader (taskorg/sim.py) knows the generated notes; this one knows nothing. It lists the
workspace, reads the first file's first two pages, proposes one part per file when asked to plan, passes
what it is asked to verify and answers ANSWER: rehearsal. It shows that workspaces, paging, the gates,
merges and verification run end to end on these files, not how well anything reads them.
"""

from __future__ import annotations

import re

from taskorg.adapters import Brief, ModelAdapter
from taskorg.live import TOOL_RESULTS
from taskorg.models import Artifact

_FILE = re.compile(r"\b([a-z0-9][a-z0-9.-]*\.txt)\b")
_PAGE = re.compile(r"\[read ([^\]\s]+) page 1 of (\d+)\]")


class BenchFake(ModelAdapter):
    name = "bench-fake"
    # The Anthropic adapter's: Claude counts about 1.75 tokens for every four characters, so the gates size the
    # filings as they will on a live run.
    token_ratio = 1.75

    def __init__(self):
        self.calls = 0

    def act(self, brief: Brief) -> Artifact:
        self.calls += 1
        results = brief.packet.split(TOOL_RESULTS, 1)[1] if TOOL_RESULTS in brief.packet else ""
        tools = brief.tools or []
        if brief.slot_function == "verifier":
            return self._art("PASS: rehearsal", "verify")
        if brief.slot_function == "lead" and brief.mode == "plan":
            files = list(dict.fromkeys(_FILE.findall(brief.packet + " " + brief.context)))[:4]
            parts = [f"subtask:part-{i}@retrieve=report what the goal asks for from {f}" for i, f in enumerate(files, 1)]
            return self._art("Plan: one part a file." if parts else "Plan: one agent.", "lead-plan", parts)
        first = "observe" if "observe" in tools else "retrieve:the" if "retrieve" in tools else ""
        if first and not results:
            return self._art("Looking first.", brief.channel_id or "lead", [first])
        if results and "read" in tools:
            page = _PAGE.search(results)
            if page and int(page.group(2)) > 1 and "page 2 of" not in results:
                return self._art("Next page.", brief.channel_id or "lead", [f"read:{page.group(1)}@2"])
            if "[read " not in results:
                first = _FILE.findall(results)
                if first:
                    return self._art("Reading.", brief.channel_id or "lead", [f"read:{first[0]}"])
        channel = "lead-merge" if brief.slot_function == "lead" else (brief.channel_id or "part")
        return self._art("Read what there was.\nANSWER: rehearsal", channel)

    @staticmethod
    def _art(claim: str, channel: str, requests: list[str] | None = None) -> Artifact:
        return Artifact(claim=claim, evidence=["rehearsal"], uncertainty="a stand-in reader", channel_id=channel,
                        context_update="", requests=requests or [])


class FakeAnthropic:
    """Stands where the Anthropic SDK client would, for CrewAI's requests: a manager delegates once to a reader,
    which lists the files, reads the first one, and answers; every reply is a real SDK Message."""

    def __init__(self):
        self.messages = self
        self.requests: list[dict] = []

    def create(self, **params):
        from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

        self.requests.append(params)
        n = len(self.requests)
        msgs = params.get("messages") or []
        tools = {t["name"]: t for t in params.get("tools") or []}
        done = sum(1 for m in msgs if isinstance(m.get("content"), list)
                   for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result")
        usage = Usage(input_tokens=max(1, len(str(params)) // 4), output_tokens=20)

        def reply(content, stop):
            return Message(id=f"msg_{n}", type="message", role="assistant", model=params.get("model", "fake"),
                           content=content, stop_reason=stop, stop_sequence=None, usage=usage)

        def call(name, **given):
            props = tools[name].get("input_schema", {}).get("properties", {})
            args = {k: given.get(k, "Reader 1" if "coworker" in k else "Read the files and report the answer.")
                    for k in props if k in given or k in ("task", "context", "coworker", "query")}
            return reply([ToolUseBlock(id=f"toolu_{n}", type="tool_use", name=name, input=args | given)], "tool_use")

        delegate = next((t for t in tools if "delegate" in t.lower()), None)
        if delegate and done == 0:
            return call(delegate)
        if "list_files" in tools and done == 0:
            return call("list_files")
        if "read_file" in tools and done == 1:
            listed = [b.get("content") for m in msgs if isinstance(m.get("content"), list)
                      for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
            names = _FILE.findall(str(listed))
            if names:
                return call("read_file", path=names[0])
        return reply([TextBlock(type="text", text="Read what there was.\nANSWER: rehearsal")], "end_turn")
