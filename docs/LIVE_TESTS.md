# Live test log

Genet's runs against real models: the first comparison pilot on Claude (27 October 2026), and 13 runs of v0.1 on xAI's endpoint (31 August and 1 September 2026). Run files and tapes stay on the operator's machine.

## 27 October 2026: comparison pilot on Claude Haiku 5.5

The first live run of `compare`: v0.5.0, `--adapter anthropic`, `claude-haiku-5-5` at effort `low`, `--per-family 2`, all four strategies, a 16,000-token per-call cap, and `--max-spend 0.50`. Every exchange is on a tape, so the run replays with no key.

| Strategy | Correct | Answer right | Calls | Tokens | Cost |
|---|---|---|---|---|---|
| single | 4 of 8 | 6 of 8 | 33 | 103,227 | $0.021 |
| always | 4 of 8 | 7 of 8 | 81 | 237,110 | $0.052 |
| genet | 4 of 8 | 6 of 8 | 46 | 130,105 | $0.028 |
| genet-stated | 1 of 8 | 6 of 8 | 60 | 192,484 | $0.042 |

"Correct" is a right answer in a run the verifier passed; "answer right" ignores the verdict. Cost is estimated from the tokens the API reported, at $0.10 and $0.50 per million. A one-task smoke test before it cost $0.002.

- **Spend.** 220 calls and 662,926 tokens (472,498 prompt, 190,428 completion, of which 79,536 were thinking): $0.14. The estimate was $0.05. Claude counted 1.39 to 1.73 times the tokens Genet estimates from characters (median 1.52), thinking added 40% to the output, and failed verdicts added rework calls. A call took 4.7 seconds at the median, 10.3 at most.
- **The verifier decided the score.** It failed 36 of 50 products, and 12 runs with the right answer ended on a failed verdict. Its reasons, read from its replies (one verdict can give several): the ANSWER marker sat at the end of a sentence, not on a line of its own (about 17); the product cited evidence the verifier had no tools to check (about 14); the notes name quarters by month and never say which months make FY2026 Q1 (about 12); no ANSWER marker at all (about 7); and the product read as the brief (about 5).
- **The product read as the brief.** After a rework, the verifier's packet held the old product in working memory and the new one in a section called BRIEF, and the verifier judged the old one: "the ANSWER line appears only in the brief". A kernel bug; the simulated reader was written to take BRIEF as the product, so the sim never showed it.
- **The answer as a key of its own.** Four replies were refused by the schema: three added `"ANSWER": "4.5%"` beside the six keys, one was broken JSON. The retry repeated the mistake, and the smoke test aborted on it. Nothing in the prompt said that `claim` is the product.
- **One wrong answer passed.** A single agent summed Halvorsen Freight, a look-alike, in place of Halvorsen Freight Labs (149.2 for 146.7), and the verifier, which cannot read the notes, passed it.
- **Genet never split.** At this cap every task fits one context, so Genet stayed a single agent, as in the simulation, at 1.26 times the single agent's tokens (the sim: 1.23). With half the runs lost to verdicts, eight tasks a strategy cannot rank the strategies.

What changed because of it (v0.5.0): the prompt says `claim` is the product and that any other key is refused, and the retry note says where its content goes; the verifier gets the product under a heading that names it, and working memory holds the reworked product; the harness asks for "ends with ANSWER: <value>", which is what grading takes, and states which months make each quarter; and the Claude adapter's size estimate is 1.75 times the character estimate. Each has a test in `tests/test_live_findings.py`. A prompt change alters every request, so the tape cannot replay the fixed version; that needs a new live run.

## 31 August and 1 September 2026: v0.1 on xAI

All 13 runs used v0.1 through the `live` adapter against xAI's endpoint. The 1 September runs used `grok-4.20-0309-non-reasoning`; the 31 August run files do not record the model name. Every run file still loads with today's code.

These runs used v0.1. The commands below use the current names: `single` was `run`, `fanout` was `split`, `replan` was `adapt`, and `--tier tight|normal|open` was `--pace crawl|walk|run`. Behavior has also changed since: a single open sub-task is now the lead's job and no longer gets its own worker.

Each table says what the product actually was, not only the verdict. The verdict was often not enough on its own: see [What the record shows](#what-the-record-shows).

### 31 August

The earlier version of this log covered only 1 September. These runs come first in time.

| Id | Task | Setup | Status | Spend | What the product was | Verdict right? |
|---|---|---|---|---|---|---|
| exists-live-1 | Write two notes; note A already on disk | `fanout`, open tier | complete | 1 sub-agent; 3 calls / 2,140 tok / 5.0s | Said it wrote only note B and skipped A | Yes |
| crawl-am-1 | Summarize a paragraph in one sentence | `single`, tight tier | complete | 2 calls / 1,482 tok / 3.1s | Restated its own instructions instead of summarizing | **No: passed** |
| job-status-1 | Write a five-line status of what Genet proved | `single`, tight tier | halt TOOLS | 1 call, not recorded | None: v0.1 read the schema word `purpose` in the reply's requests as a tool request | — |
| job-status-1b | Same | `single`, tight tier | complete | 2 calls / 1,447 tok / 3.9s | About Jean Genet the playwright | **No: passed** |
| job-status-2 | Write a five-line status from two notes, one already filed | `fanout`, open tier | complete | 1 sub-agent; 3 calls / 2,162 tok / 5.0s | One sentence about which note it used, not a five-line status | Doubtful: passed |
| job-status-1c | Same as job-status-1 | `single`, tight tier, 1,500-token cap | halt BUDGET | 1 call / 2,022 tok / 3.5s | None: the first call's 1,824-token prompt plus its reply went over the cap after it was paid for | — |
| job-status-1d | Same, cap raised to 4,000 | `single`, tight tier | halt VERIFY | 2 calls / 4,144 tok / 7.6s | About the playwright again | Right verdict, wrong reason |
| job-status-1e | Same goal, reworded to "this Genet kernel", with task-specific criteria `live proof` and `one body` | `single`, tight tier, cap 4,000 | complete | 2 calls / 4,190 tok / 4.9s | On topic | Yes |

- **job-status-1d:** the verifier said FAIL because the product "does not contain" the criteria, but they were there. It failed the right product for the wrong reason.

### 1 September: two-file folder

World: `$HOME/genet-job/note-a.txt` filed, `note-b.txt` open.

| Id | Setup | Status | Workers | Split | Spend |
|---|---|---|---|---|---|
| job-notes-1 | `fanout`; the default `--axes` still had an invalid axis | halt METHOD | 0 | — | 0 calls |
| job-notes-2 | `fanout`, `--exists` A, `--read` B, `--axes sequential,fan_in` | complete | 1 (`note-b`) | true | 3 calls / 2379 tok / 6.9s |
| job-notes-3 | `fanout`, `--exists` A and B | complete | 0 | false | 2 calls / 1396 tok / 3.9s |

- **job-notes-1:** halted before any call, but v0.1 still saved the run, as unfinished. Today a setup error writes nothing.
- **job-notes-2:** only the open sub-task got a worker. Isolation and authority flags were empty; health ok.
- **job-notes-3:** open tier (fan-out allowed), yet `decide()` still refused. Verifier 1.0; `could_this_have_been_one: true`.

### 1 September: replan and budget cap

| Id | Setup | Status | Workers | Spend |
|---|---|---|---|---|
| job-adapt-1 | `replan --tier normal`; the first outline no longer fit | complete | 0 | 2 calls / 1506 tok / 4.1s |
| job-leash-1 | `single --tier tight --max-calls 1` | abort BUDGET | 0 | 1 call / 688 tok / 2.5s |

- **job-adapt-1:** the method became "start from definitions, not from jargon". Roster unchanged; verifier 1.0; health ok.
- **job-leash-1:** `BUDGET: max_calls 1 reached`, flagged `budget_halt`. Health degraded, which is expected on an abort. Roster unchanged.

### 1 September: offline, same day

- `pytest -q` → 121 passed in 12.65s
- `python3 -m taskorg.cli policy-rl --episodes 40` → stub and learned `illegal_rate: 0`, `mean_workers: 0`, `PROPOSE_CHANNEL: 0`

### What the record shows

- **A pass said little.**
  - 12 of the 13 runs reached the model (one of those calls was never recorded), and 8 passed verification.
  - Read against their tasks, two of the passes were wrong (crawl-am-1 and job-status-1b), and one is doubtful (job-status-2).
  - Every run used default success criteria, and any reply that echoes its brief meets them. The one run with task-specific criteria and a precise goal, job-status-1e, was the one clearly correct pass.
- **Cost of a call.**
  - Prompts were 485 to 670 tokens on short tasks, and 1,820 to 1,970 with a large context.
  - Replies were 109 to 205 tokens, and a call took 1.3 to 3.9 seconds.
  - A single-agent run on a short task took two calls, about 1,400 to 1,500 tokens. Each of the three runs that split had one sub-agent and took three calls, about 2,100 to 2,400 tokens.
- **Two calls were paid for and lost.** job-status-1's call was never recorded. job-status-1c's call was sent although it could not fit.

### What changed because of it

- **Lone sub-tasks.** A lone sub-task is the lead's own work, so each of the three single-sub-agent splits above would cost two calls today, not three (v0.2).
- **Tool requests.** Only known tool names count as tool requests; a schema word such as `purpose` does not (v0.2).
- **Setup errors.** A setup error writes nothing, so a run like job-notes-1 is no longer saved (v0.3.2).
- **Failed calls.** A call that fails after it was sent stays on the record and counts toward cost (v0.3.3).
- **Size check.** The check before a call counts the system prompt and keeps room for the reply, so job-status-1c's call would not be sent (v0.3.3, v0.4.2).
- **Default criteria.** A run verified only against the default criteria carries the warning `verified_against_default_criteria` (v0.4.2).
- **Goal check.** The live verifier is told to pass a product only if it answers the goal, its subject and its question (v0.4.2). Whether a model follows that is for the next live run to show.
- **Old reply names.** The oldest runs' review answers now load in today's vocabulary (v0.4.1).

## Run files

The Claude pilot's results are in `data/compare/` and its tapes in `data/tapes/`. The run files in `data/` and `Data2/` stay on the operator's machine and are not committed. `Data2/data/` is a backup copy of `data/`. The four episodes in `data/episodic/` that have no saved run (`mx-001`, `pw-001`, `so-001`, `so-live-gate`) came from the stub adapter, not from a live model.
