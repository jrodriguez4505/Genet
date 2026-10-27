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
    ("loop.py", "tool rounds unbounded", "        for _ in range(rounds):", "        for _ in range(50):"),
    ("loop.py", "per-call token cap ignored", "            if b and used > b.max_tokens_per_call:", "            if False:"),
    ("loop.py", "replan ignores tier", 'if not verified and adapt and getattr(b, "allow_adapt", True) and', "if not verified and adapt and"),
    ("loop.py", "model names its own channel", "        elif brief.channel_id:\n            art.channel_id = brief.channel_id", "        elif False:\n            art.channel_id = brief.channel_id"),
    # sandbox
    ("tools.py", "sandbox open", "            path == root or (path.is_relative_to(root) and ", "            True or (path.is_relative_to(root) and "),
    ("tools.py", "hidden files visible", '    return name in SKIP_DIRS or name.startswith(".")', "    return False"),
    ("tools.py", "hidden files readable", 'and not any(p.startswith(".") for p in path.relative_to(root).parts))', ")"),
    ("tools.py", "walk unbounded", "                        if visited > VISIT_CAP:\n                            break\n", ""),
    ("tools.py", "retrieve scans without limit", "            if scanned > SCAN_CHARS_CAP:", "            if False:"),
    ("tools.py", "binaries readable", '        if b"\\x00" in data[:1024]:', "        if False:"),
    # model output
    ("live.py", "authority keys accepted", "    if extra & forbidden:", "    if False:"),
    ("live.py", "unknown keys accepted", "    if extra:", "    if False:"),
    # memory
    ("memory_store.py", "sibling memory visible", ' or k == f"channel:{channel_id}"', " or True"),
    ("memory_store.py", "unsafe run ids", '    if not _SAFE_ID.fullmatch(run_id or "") or ".." in run_id:', "    if False:"),
    ("memory_store.py", "run id may end in a newline", '_SAFE_ID.fullmatch(run_id or "")', '_SAFE_ID.match(run_id or "")'),
    # diagnostics and CLI
    ("diagnostics.py", "saved isolation verdict ignored", '        heard[ch].update(c.get("heard_channels") or [])', "        pass"),
    ("diagnostics.py", "quoted guidelines flagged", "                if not _NEGATED.search(blob[max(0, m.start() - 24) : m.start()]):", "                if True:"),
    ("diagnostics.py", "authority checked once per term", "                    found.append(w)\n                    break", "                    found.append(w)\n                    break\n                break"),
    ("diagnostics.py", "aborted run reads ok", '    if run.status.value == "abort":\n        flags.append("aborted")', '    if False:\n        flags.append("aborted")'),
    ("cli.py", "working memory not reset", "    store.reset_working(run.id)", "    pass"),
    ("persist.py", "old files not upgraded", '    if "state" in raw:\n        # Format 2', '    if True:\n        # Format 2'),
    ("persist.py", "oldest review answers kept", '_LEGACY_RESPONSE = {"HOLD_ORG": "KEEP_ROSTER", "CHANGE_HOW": "CHANGE_METHOD"}', "_LEGACY_RESPONSE = {}"),
    ("persist.py", "old log names kept", '    return {**e, "event": _LEGACY_EVENT.get(e.get("event"), e.get("event")), "detail": detail}', '    return e'),
    ("persist.py", "run file types unchecked", "        _check_types(raw)\n", ""),
    ("persist.py", "loaded run gets a fresh clock", 'started_at=time.time() - float(raw_b.get("elapsed") or 0),', "started_at=time.time(),"),
    # measured should-we
    ("gates.py", "declared ignored", "    if declared:\n        return \"declared\"", "    if False:\n        return \"declared\""),
    ("gates.py", "stated policy ignored", '    if policy == "stated":\n        return "stated"', '    if False:\n        return "stated"'),
    ("gates.py", "unknown material counts", "    if context_limit is None or any(s is None for s in shares):", "    if False:"),
    ("gates.py", "shared files counted twice", "    total = sum(union.values())\n", "    total = sum(sum(s.values()) for s in shares)\n"),
    ("gates.py", "room ignores measured overhead", "        room, after = max(0, context_limit - overhead), ", "        room, after = context_limit, "),
    ("diagnostics.py", "split basis hidden", '"refused", "basis", "request"):', '"refused", "request"):'),
    ("loop.py", "overhead not passed", "            overhead=self._overhead(run),\n", ""),
    ("gates.py", "split that does not fit allowed", "    if biggest > room:", "    if False:"),
    ("tools.py", "material counts whole files", "min(len(text), READ_CAP) // 4", "len(text) // 4"),
    ("gates.py", "fit check off", "    if total <= room:", "    if False:"),
    ("gates.py", "fit check inverted", "    if total <= room:", "    if total > room:"),
    ("gates.py", "should-we refusals ignored", "        open_ = [a for a in open_ if a.legal]\n", ""),
    ("tools.py", "material counts unrelated files", "            if path.stem.lower() in wanted or path.name.lower() in wanted:", "            if True:"),
    # review findings: concurrency and run state
    ("loop.py", "siblings keep running", "            except BaseException as e:\n                self._abort(run, e)\n                raise\n\n        if self.parallel", "            except BaseException as e:\n                raise\n\n        if self.parallel"),
    ("loop.py", "aborts only on invariants", "        except BaseException as e:\n            self._abort(run, e)\n            self._team_review(run, e)", "        except InvariantError as e:\n            self._abort(run, e)\n            self._team_review(run, e)"),
    ("loop.py", "in-flight calls not counted", "            if b is None or n == 0:\n                return", "            if True:\n                return"),
    ("loop.py", "tools run past the budget", "                with self._lock:\n                    run.assert_running()\n                out = self.toolbox.run(req)", "                out = self.toolbox.run(req)"),
    ("run.py", "a later halt overwrites the first", "        if self.status not in (Status.COMPLETE, Status.ABORT):\n            self.stop_reason = reason", "        if True:\n            self.stop_reason = reason"),
    ("run.py", "a complete run can be aborted", '        if self.status == Status.COMPLETE:\n            raise InvariantError("CLOSED", "run is complete', '        if False:\n            raise InvariantError("CLOSED", "run is complete'),
    ("run.py", "roster change needs budget", "        self._assert_open()\n        if actor_id != self.state.lead_id and not human_override:", "        self.assert_running()\n        if actor_id != self.state.lead_id and not human_override:"),
    # review findings: budgets and decisions
    ("loop.py", "work leaves the verifier no call", "            rounds = max(0, min(rounds, self._calls_left(run) - 1 - reserve))", "            rounds = rounds"),
    ("loop.py", "merge not paid for", "            calls_after_split=self._merge_cost() + 1,", "            calls_after_split=2,"),
    ("loop.py", "verdict by prefix and substring", '    if verdict(check.claim) != "PASS":', '    if not check.claim.strip().upper().startswith("PASS") or "FAIL" in check.claim.upper():'),
    ("loop.py", "criteria by substring", "        if token and _criterion(token).search(blob):", "        if token and token in blob:"),
    ("loop.py", "fanout drops refused parts", 'extra = "integrate isolated artifacts; do not invent subtasks." + self._cover(run, verdicts, failed)', 'extra = "integrate isolated artifacts; do not invent subtasks."'),
    ("compare.py", "crew drops parts silently", '                a.refuse("could_we", problem)\n', "                continue\n"),
    ("compare.py", "best baseline can be a variant", "        best = max((s for s in BASELINES if s in overall),", '        best = max((s for s in strategies if s != "genet"),'),
    ("suite.py", "answer marker in any case", '_ANSWER = re.compile(r"(?<![A-Za-z])ANSWER:[ \\t]*([^\\n]+)")', '_ANSWER = re.compile(r"(?<![A-Za-z])ANSWER:[ \\t]*([^\\n]+)", re.IGNORECASE)'),
    ("suite.py", "a range grades as its first number", "        return len(nums) == 1 and", "        return bool(nums) and"),
    # review findings: tools and the live endpoint
    ("tools.py", "path errors crash tools", "_PATH_ERRORS = (OSError, ValueError, RuntimeError)", "_PATH_ERRORS = (OSError,)"),
    ("tools.py", "search terms unbounded", "if t))[:MAX_TERMS]", "if t))"),
    ("tools.py", "snippet found in the lowered line", "    m = pattern.search(line)\n", "    m = pattern.search(line.lower())\n"),
    ("live.py", "headers can drip forever", "            timer.start()\n", ""),
    ("live.py", "error body read crashes", '            except (OSError, http.client.HTTPException, ValueError):\n                detail = ""', '            except ():\n                detail = ""'),
    ("live.py", "usage must be an object", "        usage = usage if isinstance(usage, dict) else {}\n", "        usage = usage or {}\n"),
    ("live.py", "timeout unchecked", "    if not lo <= timeout <= hi:", "    if False:"),
    ("live.py", "claim coerced to text", "    if not isinstance(claim, str) or not claim.strip():", "    claim = str(claim)\n    if not claim.strip():"),
    # review findings: CLI, policy, bench
    ("cli.py", "out may be a directory", "    if out.is_dir():", "    if False:"),
    ("cli.py", "a crash is not saved", '    except Exception as e:\n        return None, _save_halt(run, out, InvariantError("CRASH"', '    except InvariantError as e:\n        return None, _save_halt(run, out, InvariantError("CRASH"'),
    ("cli.py", "nan switches a cap off", "        if not math.isfinite(value) or value < least", "        if value < least"),
    ("policy.py", "nan confidence passes", "        self.confidence = max(0.0, min(1.0, c)) if math.isfinite(c) else 0.0", "        self.confidence = max(0.0, min(1.0, c))"),
    ("bench.py", "an empty bench passes", '"ok": bool(checks) and all(', '"ok": all('),
    # token usage
    ("loop.py", "an unreported reply counted by its claim", "        completion = reported_completion or _reply_estimate(art)", "        completion = reported_completion or max(1, len(art.claim) // 4)"),
    ("loop.py", "an estimate passes as reported", "        usage_real = bool(reported_prompt or reported_completion) and not usage.get(\"estimated\")", "        usage_real = bool(reported_prompt or reported_completion)"),
    ("loop.py", "no reply cap set", "                brief = replace(brief, max_reply_tokens=max(1, b.max_tokens_per_call - size))", "                pass"),
    ("loop.py", "the reply cap ignores the brief", "max_reply_tokens=max(1, b.max_tokens_per_call - size)", "max_reply_tokens=b.max_tokens_per_call"),
    ("live.py", "the reply cap is not sent", "            payload[self.max_reply_param] = int(brief.max_reply_tokens)", "            pass"),
    ("live.py", "no wire estimate without usage", '                "completion_tokens": c if _count(c) else max(1, -(-len(content) // 4)),', '                "completion_tokens": c if _count(c) else None,'),
    ("live.py", "estimates not marked", '                "estimated": True,\n', ""),
    ("live.py", "any reply-cap field name accepted", "        if max_reply_param is not None and not _PARAM_NAME.fullmatch(max_reply_param):", "        if False:"),
    # shared ownership
    ("loop.py", "a part failure stops the run", "                if e.code in PART_FAILURES and run.status == Status.ACTIVE:", "                if False:"),
    ("loop.py", "authority violations absorbed", 'PART_FAILURES = ("SCHEMA", "LIVE")', 'PART_FAILURES = ("SCHEMA", "LIVE", "ROSTER", "TOOLS", "INV-1")'),
    ("loop.py", "a failed part is not handed to the lead", "        if failed:\n            text += f\" These parts' sub-agents failed", "        if False:\n            text += f\" These parts' sub-agents failed"),
    ("loop.py", "a sibling's consequence surfaces", "raise next((e for e in errors if _stop_reason(e) == run.stop_reason), errors[0])", "raise errors[0]"),
    ("loop.py", "no review after a stopped run", "            self._team_review(run, e)\n            raise", "            raise"),
    ("loop.py", "no review after a recovered run", "        self._team_review(run, None)\n        return result", "        return result"),
    ("loop.py", "lessons written when off", "            if self.lessons:\n                for lesson", "            if True:\n                for lesson"),
    ("loop.py", "a review can change the outcome", "        except Exception as e:  # never mask the run's own outcome", "        except ZeroDivisionError as e:  # never mask the run's own outcome"),
    ("memory_store.py", "lessons repeated, not counted", "            seen = [(lesson, count)] + [(text, n) for text, n in seen if text != lesson]", "            seen = [(lesson, 1)] + seen"),
    ("memory_store.py", "lessons unbounded", "for t, n in seen[:MAX_LESSONS])", "for t, n in seen)"),
    ("review.py", "an interrupt is reviewed", "    if isinstance(error, KeyboardInterrupt):\n        return None", "    if False:\n        return None"),
    # follow-ups
    ("loop.py", "failed calls go unrecorded", "                run.record_call(call)\n            raise", "            raise"),
    ("atomic.py", "a save writes in place first", "    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644\n", "    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644\n    path.write_text(text, encoding=\"utf-8\")\n"),
    ("atomic.py", "a failed save leaves its temp file", "            os.unlink(tmp)\n", "            pass\n"),
    ("run.py", "a closed note can be re-answered", '        if note.status == NoteStatus.CLOSED:\n            raise InvariantError("REVIEW"', '        if False:\n            raise InvariantError("REVIEW"'),
    ("live.py", "size check ignores the system prompt", '        chars = sum(len(m["content"]) for m in self._payload(brief)["messages"])\n        return max(1, -(-chars // 4)) + 8  # plus message framing', "        return super().estimate_tokens(brief)"),
    # security: untrusted input stays bounded
    ("live.py", "redirects followed", "build_opener(_NoRedirect, _DeadlineHTTP, _DeadlineHTTPS)", "build_opener(_DeadlineHTTP, _DeadlineHTTPS)"),
    ("live.py", "key copied on redirect", 'req.add_unredirected_header("Authorization",', 'req.add_header("Authorization",'),
    ("live.py", "plain http allowed", '    if host and parts.scheme == "https":', "    if host:"),
    ("live.py", "response size unbounded", "        if total > limit:", "        if False:"),
    ("live.py", "no read deadline", "        if time.monotonic() > deadline:\n", "        if False:\n"),
    ("live.py", "deep JSON crashes", "        except (ValueError, RecursionError) as e:  # includes", "        except ValueError as e:  # includes"),
    ("loop.py", "oversized brief sent", "            if b and size + reply > b.max_tokens_per_call:", "            if False:"),
    ("loop.py", "the gate ignores the reply room", "+ max(int(c.get(\"completion_tokens\") or 0), self._reply_room(run))", "+ int(c.get(\"completion_tokens\") or 0)"),
    ("loop.py", "no room left for the reply", "            if b and size + reply > b.max_tokens_per_call:", "            if b and size > b.max_tokens_per_call:"),
    ("live.py", "live reply room is zero", "    min_reply_tokens = 200\n", "    min_reply_tokens = 0\n"),
    ("loop.py", "malformed replies not retried", '            if e.code != "SCHEMA" or run.status != Status.ACTIVE:\n                raise', "            raise"),
    ("loop.py", "authority violations retried", '            if e.code != "SCHEMA" or run.status != Status.ACTIVE:', '            if e.code not in ("SCHEMA", "ROSTER") or run.status != Status.ACTIVE:'),
    ("loop.py", "the retry gives no reason", "replace(brief, packet=brief.packet + RETRY_NOTE)", "replace(brief, packet=brief.packet)"),
    ("review.py", "a recovered retry leaves no review", "    if retries:\n        note(", "    if False:\n        note("),
    ("diagnostics.py", "default criteria pass silently", '    warnings = ["verified_against_default_criteria"] if default_criteria(run) else []', "    warnings = []"),
    ("live.py", "the verifier ignores the goal", "PASS only if the product answers the goal, its subject and its question, and meets every success", "PASS only if the product meets every success"),
    ("loop.py", "tool requests unbounded", "            if len(wanted) > MAX_TOOL_REQUESTS:", "            if False:"),
    ("loop.py", "proposals unbounded", "        if len(subtasks) > MAX_PROPOSALS:", "        if False:"),
    ("loop.py", "bad token counts accepted", "    if isinstance(value, bool) or not isinstance(value, int) or value < 0:", "    if False:"),
    ("persist.py", "saved tools trusted", '    saved["tools"] = [t for t in saved.get("tools") or [] if t in allowed]', '    saved["tools"] = saved.get("tools") or []'),
    ("persist.py", "malformed run file crashes", "    except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as e:", "    except ():"),
    ("tools.py", "material ignores the note", "        wanted = {channel.lower()} | names", "        wanted = {channel.lower()}"),
    ("loop.py", "isolation flag ignored", "            declared=declared or self.isolation_required,", "            declared=declared,"),
    ("loop.py", "operator fan-out not declared", "        verdicts = self._assess(run, subtasks, declared=True)\n", "        verdicts = self._assess(run, subtasks)\n"),
    ("loop.py", "context limit not passed", "            context_limit=b.max_tokens_per_call if b else None,", "            context_limit=None,"),
    ("sim.py", "sim reads a file per mention", "    return list(dict.fromkeys(s for _, s in sorted(found)))", "    return [s for _, s in sorted(found)]"),
    # anthropic adapter, tapes, spend cap
    ("anthropic_live.py", "temperature sent", "            # No temperature: current Claude models reject one.\n", '            "temperature": 0,\n'),
    ("anthropic_live.py", "key from any variable", 'os.environ.get("TASKORG_ANTHROPIC_KEY", "")', 'os.environ.get("ANTHROPIC_API_KEY", "")'),
    ("anthropic_live.py", "live endpoint gets the key", 'os.environ.get("TASKORG_ANTHROPIC_BASE", "")', 'os.environ.get("TASKORG_MODEL_BASE", "")'),
    ("anthropic_live.py", "sdk follows redirects", "follow_redirects=False", "follow_redirects=True"),
    ("anthropic_live.py", "refusal passes", '        if getattr(msg, "stop_reason", None) == "refusal":', "        if False:"),
    ("anthropic_live.py", "reply cap unbounded", "min(int(brief.max_reply_tokens or DEFAULT_MAX_REPLY), MAX_REPLY_CEILING)",
     "int(brief.max_reply_tokens or DEFAULT_MAX_REPLY)"),
    ("tape.py", "cap in the request key", "    body = {k: v for k, v in payload.items() if k != cap_field}", "    body = payload"),
    ("tape.py", "tape written over", 'self.path.open("x", encoding="utf-8")', 'self.path.open("w", encoding="utf-8")'),
    ("tape.py", "any error code replayed", 'error.get("code") in ERROR_CODES', 'isinstance(error.get("code"), str)'),
    ("tools.py", "absolute paths shown", "                if self._resolve(rel) == resolved:\n                    return rel\n", ""),
    ("tools.py", "ambiguous relative name", "                if self._resolve(rel) == resolved:", "                if True:"),
    ("compare.py", "spend cap looks back only", "        if costs and spent + max(costs) > max_spend:", "        if False:"),
    ("compare.py", "spend cap off", '                        reason = stop_when(results) if stop_when else ""', '                        reason = ""'),
    ("cli.py", "spend cap without prices", "    if args.max_spend is not None and args.price_in is None:", "    if False:"),
    # findings from the Haiku 5.5 pilot
    ("loop.py", "rework product not remembered",
     "            # The reworked product replaces the last one everywhere the verifier looks.\n            self.store.remember_working(run.id, \"product\", product.claim)\n", ""),
    ("loop.py", "product under review unnamed",
     'f"PRODUCT UNDER REVIEW (the lead\'s current product, the same as WORKING product)\\n{extra}\\n" if extra else ""',
     'f"{extra}\\n" if extra else ""'),
    ("live.py", "claim not named the product", "  claim (string): your product, all of it. When the brief says how the product must end, claim ends that way.\n",
     "  claim (string),\n"),
    ("compare.py", "fiscal calendar unstated",
     '    "FY2026 is calendar 2026: Q1 is January to March, Q2 April to June, Q3 July to September, Q4 October to December. "\n', ""),
    ("anthropic_live.py", "claude estimate uncalibrated", "        return math.ceil((max(1, -(-chars // 4)) + 8) * TOKEN_RATIO)",
     "        return max(1, -(-chars // 4)) + 8"),
    ("loop.py", "proposals split on spaces", "        return parse_proposals(plan.requests)", '        return __import__("taskorg.subtasks").subtasks.parse_subtasks(" ".join(plan.requests))'),
    ("compare.py", "crew proposals split on spaces", "        return parse_proposals(plan.requests)", '        return __import__("taskorg.subtasks").subtasks.parse_subtasks(" ".join(plan.requests))'),
    ("subtasks.py", "one proposal per request", "        for body in _MARK.split(request.strip())[1:]:", "        for body in request.strip().split(\"subtask:\")[1:2]:"),
    ("loop.py", "placeholder plan template", "subtask:CHANNEL@SKILL=NAMED_FAILURE, for example", "'subtask:<channel>@<skill>=<named_failure>', for example"),
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
