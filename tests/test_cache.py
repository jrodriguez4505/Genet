"""Prompt caching (TASKORG_MODEL_CACHE): a call that may go on to tool rounds is sent in blocks, cut where each round
begins, with the newest round marked, so the next round reads what came before from the cache. The model reads the
same text, the kernel's size checks see the same size, and a cache read or write is priced apart."""

import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from taskorg.adapters import TOOL_RESULTS, Brief
from taskorg.anthropic_live import AnthropicAdapter
from taskorg.compare import CACHE_READ, CACHE_WRITE, trial_cost
from taskorg.errors import InvariantError
from taskorg.live import message_text, user_blocks, user_message
from taskorg.tape import Player, Recorder, replay_adapter


def _brief(rounds=0, tools=("read",), packet='PLAN "quoted" — dash\nline two'):
    for i in range(rounds):
        packet += f"\n{TOOL_RESULTS}\n[read f{i}.md]\nRevenue was $1{i}.0M…"
    return Brief("lead", "retrieve", packet, "goal", "purpose", "context", "done", tools=list(tools), mode="work")


class Client:
    def __init__(self, cached=(0, 0)):
        self.sent, self.cached = [], cached

    @property
    def messages(self):
        outer = self

        class M:
            @staticmethod
            def create(**payload):
                outer.sent.append(payload)
                write, read = outer.cached
                return NS(content=[NS(type="text", text='{"claim": "ANSWER: 1"}')], stop_reason="end_turn",
                          usage=NS(input_tokens=100, output_tokens=20, cache_creation_input_tokens=write,
                                   cache_read_input_tokens=read))
        return M


@pytest.mark.parametrize("rounds", [0, 1, 3])
def test_the_blocks_are_the_same_text(rounds):
    brief = _brief(rounds)
    blocks = user_blocks(brief)
    assert "".join(blocks) == user_message(brief) and len(blocks) == rounds + 2 and all(blocks)


def test_a_call_with_tools_is_sent_in_blocks_with_the_newest_round_marked():
    adapter = AnthropicAdapter("k", "m", client=Client(), cache=True)
    content = adapter._payload(_brief(2))["messages"][0]["content"]
    assert [("cache_control" in b) for b in content] == [False, False, True, False]
    assert message_text(content) == user_message(_brief(2))


def test_a_call_with_no_tools_and_a_run_without_caching_send_one_string():
    on, off = AnthropicAdapter("k", "m", client=Client(), cache=True), AnthropicAdapter("k", "m", client=Client())
    assert isinstance(on._payload(_brief(0, tools=()))["messages"][0]["content"], str)  # a verifier: no round follows
    assert off._payload(_brief(2))["messages"][0]["content"] == user_message(_brief(2))
    assert off.cache is False


@pytest.mark.parametrize("rounds", [0, 2])
def test_the_size_the_kernel_checks_does_not_change(rounds):
    on, off = AnthropicAdapter("k", "m", client=Client(), cache=True), AnthropicAdapter("k", "m", client=Client())
    assert on.estimate_tokens(_brief(rounds)) == off.estimate_tokens(_brief(rounds))


def test_what_a_cache_wrote_and_read_is_kept_apart():
    adapter = AnthropicAdapter("k", "m", client=Client(cached=(300, 500)), cache=True)
    adapter.act(_brief(1))
    assert adapter.last_usage == {"prompt_tokens": 900, "completion_tokens": 20, "cache_write_tokens": 300,
                                  "cache_read_tokens": 500}


def test_a_cache_read_costs_a_tenth_and_a_write_a_quarter_more():
    r = NS(prompt_tokens=1_000, completion_tokens=100, cache_write_tokens=400, cache_read_tokens=500)
    assert trial_cost(r, 0.10, 0.50) == pytest.approx(((100 + CACHE_WRITE * 400 + CACHE_READ * 500) * 0.10 + 100 * 0.50) / 1e6)
    plain = NS(prompt_tokens=1_000, completion_tokens=100)
    assert trial_cost(plain, 0.10, 0.50) == pytest.approx((1_000 * 0.10 + 100 * 0.50) / 1e6)


def test_a_tape_says_it_was_cached_and_replays_so(tmp_path: Path):
    adapter = AnthropicAdapter("k", "m", client=Client(), cache=True)
    assert adapter.tape_header()["cache"] is True and "cache" not in AnthropicAdapter("k", "m", client=Client()).tape_header()
    tape = tmp_path / "t.jsonl"
    rec = Recorder(tape, adapter.tape_header())
    adapter.tape = rec
    adapter.act(_brief(1))
    rec.close()
    again = replay_adapter(Player(tape))
    assert again.cache is True and again.act(_brief(1)).claim == "ANSWER: 1"


def test_a_tape_cannot_say_anything_else_of_its_cache(tmp_path: Path):
    tape = tmp_path / "t.jsonl"
    tape.write_text(json.dumps({"tape": 1, "adapter": "anthropic", "model": "m", "cache": "yes"}) + "\n")
    with pytest.raises(InvariantError):
        Player(tape)


def test_a_run_keeps_what_its_calls_cached(tmp_path: Path):
    from taskorg.adapters import ModelAdapter
    from taskorg.budget import Budget
    from taskorg.factory import new_run
    from taskorg.loop import Engine
    from taskorg.memory_store import MemoryStore
    from taskorg.models import Artifact

    class Cached(ModelAdapter):
        name = "cached"

        def act(self, brief):
            self.last_usage = {"prompt_tokens": 900, "completion_tokens": 20, "cache_write_tokens": 300, "cache_read_tokens": 500}
            return Artifact(claim="ANSWER: 1", evidence=["e"], uncertainty="u", channel_id="", context_update="", requests=[])

    run = new_run("r", goal="g", purpose="p", done_when="d")
    run.state.success_criteria = ["ANSWER:"]
    e = Engine(MemoryStore(tmp_path / "s"), adapter=Cached(), budget=Budget(max_calls=5))
    e._arm(run)
    e._act(run, e._brief(run, "lead", extra="WORK.", mode="work"))
    assert run.calls[-1]["cache_write_tokens"] == 300 and run.calls[-1]["cache_read_tokens"] == 500


def test_the_benches_read_a_cached_tape(tmp_path: Path):
    from taskorg import merge_bench

    content = [{"type": "text", "text": t} for t in user_blocks(_brief(1))]
    assert json.loads(message_text(content))["packet"].startswith("PLAN")
    assert "message_text" in Path(merge_bench.__file__).read_text()
