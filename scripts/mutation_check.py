"""Mutation check: break one rule at a time and confirm some test fails.

    python scripts/mutation_check.py                    # all mutations
    python scripts/mutation_check.py "fit check off"    # one, or several separated by |

Each mutation replaces one exact snippet in taskorg/, runs the suite (stopping at the
first failure), and restores the file. A mutation that no test catches is a rule the
suite does not protect. When you add a rule, add a mutation for it here.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

M = [
    # gates
    ("gates.py", "world covers channel", "    if subtask.channel_id in world.existing_channels:", "    if False:"),
    ("gates.py", "file match by substring", "Path(path).stem.lower() == subtask.channel_id.lower()", "subtask.channel_id.lower() in path.lower()"),
    ("gates.py", "duplicate proposal allowed", "if not covered and subtask.channel_id in seen:", "if False:"),
    ("gates.py", "verify sub-task allowed", 'if not covered and subtask.skill == "verify":', "if False:"),
    ("gates.py", "no named failure allowed", "        if not failure:", "        if False:"),
    ("gates.py", "unknown skill allowed", "    if subtask.skill not in SKILLS:", "    if False:"),
    ("gates.py", "reserved channel allowed", "    if subtask.channel_id in RESERVED_CHANNELS:", "    if False:"),
    ("gates.py", "lone sub-task gets a worker", "    if len(open_) == 1:", "    if False:"),
    ("gates.py", "tier ignored", "    if len(open_) >= 2 and not allow_split:", "    if False:"),
    ("gates.py", "budget off-by-one", "spend + c > calls_left - calls_after_split", "spend + c > calls_left - calls_after_split + 1"),
    ("gates.py", "worker cap ignored", "for a in open_[: max(0, worker_slots_left)]:", "for a in open_:"),
    # gate record
    ("models.py", "GATE-1 not enforced", "        if self.can_someone_else:", "        if False:"),
    ("models.py", "gate order not enforced", "        if self.order != GATE_ORDER:", "        if False:"),
    # roster
    ("run.py", "anyone may set the roster", "if actor_id != self.state.lead_id and not human_override:", "if False:"),
    ("run.py", "re-tasking needs no gates", " or old_workers[s.id] != s.channel_id]", "]"),
    ("run.py", "duplicate slot ids allowed", "        if len(ids) != len(set(ids)):", "        if False:"),
    ("run.py", "two workers per write", "            if len(added) > 1:", "            if False:"),
    ("run.py", "worker channel need not match gate", "if gates.channel_id and s.channel_id != gates.channel_id:", "if False:"),
    ("run.py", "pre-call budget off-by-one", "        if calls >= b.max_calls:", "        if calls > b.max_calls:"),
    ("run.py", "post-call budget too strict", "        if calls > b.max_calls:", "        if calls >= b.max_calls:"),
    ("run.py", "replan answerable with KEEP_ROSTER", 'if note.kind == "replan" and response not in ("CHANGE_METHOD", "REVISE_GOAL"):', "if False:"),
    ("run.py", "note ids reusable", "        if note_id in self.notes:\n            raise InvariantError(\"REVIEW\", f\"note id already used: {note_id}\")\n        note = ReviewNote", "        note = ReviewNote"),
    ("run.py", "closed runs writable", '            raise InvariantError("CLOSED", f"run is {self.status.value}; the board is a record now")', "            return"),
    ("run.py", "complete with open review", "        if self.open_review_ids():\n            raise InvariantError(\"INV-4\"", "        if False:\n            raise InvariantError(\"INV-4\""),
    ("run.py", "anyone may update context", '        if actor_id != self.state.lead_id:\n            raise InvariantError("INV-1", "only the lead may update the context")', '        if False:\n            raise InvariantError("INV-1", "only the lead may update the context")'),
    ("run.py", "reviewer may take a skill", '        if slot.function == "reviewer":', "        if False:"),
    # engine
    ("loop.py", "criteria pass by echo", '    blob = " ".join(parts).lower()', '    blob = " ".join(parts + list(criteria)).lower()'),
    ("loop.py", "isolation never detected", "    return heard\n", "    return []\n"),
    ("loop.py", "sub-agents see live context", "context=split_context, mode=\"work\"", "context=None, mode=\"work\""),
    ("loop.py", "tool allowlist not checked", "                    run.assert_tools(slot_id, toolish)", "                    pass"),
    ("loop.py", "tool rounds unbounded", "        for _ in range(self.max_tool_rounds):", "        for _ in range(50):"),
    ("loop.py", "per-call token cap ignored", "            if b and used > b.max_tokens_per_call:", "            if False:"),
    ("loop.py", "replan ignores tier", 'if not verified and adapt and getattr(b, "allow_adapt", True) and', "if not verified and adapt and"),
    ("loop.py", "model names its own channel", "        elif brief.channel_id:\n            art.channel_id = brief.channel_id", "        elif False:\n            art.channel_id = brief.channel_id"),
    # sandbox
    ("tools.py", "sandbox open", "        return any(path == root or path.is_relative_to(root) for root in self.roots)", "        return True"),
    ("tools.py", "hidden files visible", "if any(part in SKIP_DIRS or part.startswith(\".\") for part in path.relative_to(top).parts):", "if False:"),
    ("tools.py", "binaries readable", '        if b"\\x00" in data[:1024]:', "        if False:"),
    # model output
    ("live.py", "authority keys accepted", "    if extra & forbidden:", "    if False:"),
    ("live.py", "unknown keys accepted", "    if extra:", "    if False:"),
    # memory
    ("memory_store.py", "sibling memory visible", ' or k == f"channel:{channel_id}"', " or True"),
    ("memory_store.py", "unsafe run ids", '    if not _SAFE_ID.match(run_id or "") or ".." in run_id:', "    if False:"),
    # diagnostics and CLI
    ("diagnostics.py", "saved isolation verdict ignored", '        heard[ch].update(c.get("heard_channels") or [])', "        pass"),
    ("diagnostics.py", "quoted guidelines flagged", 'if any(neg in window for neg in ("not ", "may not ", "cannot ", "can\'t ", "do not ", "don\'t ")):', "if False:"),
    ("cli.py", "working memory not reset", "    store.reset_working(run.id)", "    pass"),
    ("persist.py", "old files not upgraded", '    if "state" in raw:\n        return raw', "    if True:\n        return raw"),
    # measured should-we
    ("gates.py", "declared ignored", "    if declared:\n        return \"declared\"", "    if False:\n        return \"declared\""),
    ("gates.py", "stated policy ignored", '    if policy == "stated":\n        return "stated"', '    if False:\n        return "stated"'),
    ("gates.py", "unknown material counts", "    if context_limit is None or any(s is None for s in shares):", "    if False:"),
    ("gates.py", "shared files counted twice", "    total = sum(union.values())\n", "    total = sum(sum(s.values()) for s in shares)\n"),
    ("gates.py", "room ignores measured overhead", "        room, after = max(0, context_limit - overhead), ", "        room, after = context_limit, "),
    ("diagnostics.py", "split basis hidden", '"refused", "basis", "request"):', '"refused", "request"):'),
    ("loop.py", "overhead not passed", "            overhead=self._overhead(run),\n", ""),
    ("gates.py", "split that does not shrink allowed", "    if max(sum(share.values()) for share in shares) >= total:", "    if False:"),
    ("gates.py", "fit check off", "    if total <= room:", "    if False:"),
    ("gates.py", "fit check inverted", "    if total <= room:", "    if total > room:"),
    ("gates.py", "should-we refusals ignored", "        open_ = [a for a in open_ if a.legal]\n", ""),
    ("tools.py", "material counts unrelated files", "            if path.stem.lower() in wanted or path.name.lower() in wanted:", "            if True:"),
    ("tools.py", "material ignores the note", '        wanted = {channel.lower()} | {n.lower() for n in re.findall(r"[\\w.-]+\\.\\w+", note)}', "        wanted = {channel.lower()}"),
    ("loop.py", "isolation flag ignored", "            declared=declared or self.isolation_required,", "            declared=declared,"),
    ("loop.py", "operator fan-out not declared", "        verdicts = self._assess(run, subtasks, declared=True)\n", "        verdicts = self._assess(run, subtasks)\n"),
    ("loop.py", "context limit not passed", "            context_limit=b.max_tokens_per_call if b else None,", "            context_limit=None,"),
    ("sim.py", "sim reads a file per mention", "    return list(dict.fromkeys(s for _, s in sorted(found)))", "    return [s for _, s in sorted(found)]"),
]


def main(argv: list[str]) -> int:
    ONLY = set(argv[0].split("|")) if argv else None
    survivors, stale, ran = [], [], 0
    for fname, name, old, new in M:
        if ONLY and name not in ONLY:
            continue
        path = ROOT / "taskorg" / fname
        src = path.read_text()
        if src.count(old) != 1:
            # The code moved under the mutation: it no longer tests anything, so it fails the check.
            print(f"STALE    {fname:<15} {name}: snippet found {src.count(old)} times", flush=True)
            stale.append(name)
            continue
        ran += 1
        path.write_text(src.replace(old, new))
        try:
            r = subprocess.run([PY, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                               capture_output=True, text=True, timeout=240, env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"})
            killed = r.returncode != 0
        except subprocess.TimeoutExpired:
            killed = True
        finally:
            path.write_text(src)
        print(f"{'killed  ' if killed else 'SURVIVED'} {fname:<15} {name}", flush=True)
        if not killed:
            survivors.append(name)
    print(f"\n{ran - len(survivors)} of {ran} mutations caught; uncaught: {survivors}")
    if stale:
        print(f"stale (update the snippet): {stale}")
    return 1 if survivors or stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
