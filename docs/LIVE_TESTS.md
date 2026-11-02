# Live test log

Genet's runs against real models: the first comparison pilot on Claude, two reruns with fixes, 16-trial runs on Haiku 5.5 and Sonnet 5.5, three runs at a tight cap, and the concept experiments (27 October 2026), the aggregate rerun and the verify bench (28 and 29 October), reporting up, the cards, the verifier arms and their follow-up (2 November), and 13 runs of v0.1 on xAI's endpoint (31 August and 1 September 2026). The tapes and results through 29 October are published as a GitHub release, [tapes-20261029](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261029), with a replay command for each; the run files in `data/` stay on the operator's machine.

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
- **Genet never split.** At this cap every task fits one context, so Genet stayed a single agent, as in the simulation, at 1.26 times the single agent's tokens (the sim: 1.25). With half the runs lost to verdicts, eight tasks a strategy cannot rank the strategies.

What changed because of it (v0.5.0): the prompt says `claim` is the product and that any other key is refused, and the retry note says where its content goes; the verifier gets the product under a heading that names it, and working memory holds the reworked product; the harness asks for "ends with ANSWER: <value>", which is what grading takes, and states which months make each quarter; and the Claude adapter's size estimate is 1.75 times the character estimate. Each has a test in `tests/test_live_findings.py`. A prompt change alters every request, so the tape cannot replay the fixed version; that needs a new live run.

## 27 October 2026: the same pilot, rerun with the fixes

The same 32 trials on Haiku 5.5, with the four fixes above.

| Strategy | Correct | Answer right | Calls | Tokens | Cost |
|---|---|---|---|---|---|
| single | 8 of 8 | 8 of 8 | 24 | 72,588 | $0.014 |
| always | 8 of 8 | 8 of 8 | 55 | 197,702 | $0.038 |
| genet | 8 of 8 | 8 of 8 | 37 | 110,931 | $0.024 |
| genet-stated | 6 of 8 | 7 of 8 | 35 | 94,273 | $0.021 |

- **Spend.** 151 calls and 475,494 tokens (351,672 prompt, 123,822 completion, of which 46,023 were thinking): $0.097, against $0.14 before. The smoke test passed in 3 calls for $0.001.
- **The verifier.** 34 verdicts, 31 PASS. Of the 3 FAILs, one caught a real error: a product that summed Halvorsen Freight in place of Halvorsen Freight Labs, which the rework then fixed. Reworks fell from 33 to 4.
- **One wrong answer still passed.** genet-stated made the same Halvorsen Freight substitution, and that verdict passed it. The verifier has no tools, so it cannot check a figure against the notes.
- **The answer key, three times.** Three replies still added an `ANSWER` key; the retry recovered all three.
- **Genet stayed single at 1.53 times the single agent's tokens.** Every task fit one context, as before. A real model's planning call costs about as much as a working call, where the simulated reader's is cheaper (1.25 times there). With a roomy context, that planning call is the whole of Genet's overhead.
- **The crew was not always a crew.** In 3 of its 8 trials, every proposal was refused and the lead did the work: Haiku copied the plan prompt's `<channel>` placeholder literally, left the channel empty, or named a part `lead`. Genet's own plans did the same (`<channel>`, `workspace`, `unassigned`); the gates refused them, as they would at this cap anyway.
- **Workers got one word of their note.** The kernel joined the lead's proposals and split them on spaces, so `subtask:orbrook@retrieve=Open orbrook.md, find the Q1 revenue` reached the worker as "Open". The workers still answered right, from their channel name and the goal.

What changed because of it (v0.5.0): proposals are read one request at a time, keeping their spaces; both plan prompts show a real proposal instead of placeholders and say to name a part's channel after the file it reads. Tests are in `tests/test_live_findings.py`. These change the planning prompts, so their effect needs another live run.

## 27 October 2026: second rerun, with the planning fixes

The same 32 trials on Haiku 5.5, with proposals read whole and plan prompts that show a real proposal.

| Strategy | Correct | Answer right | Calls | Tokens | Cost |
|---|---|---|---|---|---|
| single | 8 of 8 | 8 of 8 | 24 | 73,454 | $0.015 |
| always | 7 of 8 | 7 of 8 | 72 | 174,295 | $0.040 |
| genet | 8 of 8 | 8 of 8 | 38 | 117,159 | $0.024 |
| genet-stated | 6 of 8 | 8 of 8 | 56 | 179,476 | $0.039 |

- **Spend.** 190 calls and 544,384 tokens (387,545 prompt, 156,839 completion, of which 60,455 were thinking): $0.12. The three Haiku runs and their smoke tests came to $0.36 in all.
- **The planning fixes held.** The crew staffed workers in all 8 trials, against 5 before. Workers got notes of 5 to 33 words (median 22), not one word. Every proposed channel was a real name, most of them the file the part reads; none was a placeholder.
- **The crew's one miss was the crew's own.** Its lead also staffed a checker with skill `verify` and no tools. The checker said it could not confirm the figure, and the lead trusted that over the worker that had quoted the file, so the product said "not confirmed". Genet's gates refuse a verify part for this reason: checking is the verifier's job, not a worker's.
- **The verifier.** 37 verdicts, 29 PASS. Of the 8 FAILs, 4 were right: the crew's unconfirmed product, twice, and the Halvorsen Freight substitution, twice, one of which the rework then fixed. 3 failed a right product because it showed no sources: the verifier gets the product's text and not the evidence the lead gave with it.
- **Genet stayed single at 1.60 times the single agent's tokens**, and the crew cost 2.37 times. Every task still fit one context.
- **The answer key, once.** One worker added an `ANSWER` key; the retry recovered it.

What changed because of it (v0.5.0): the verifier reads the evidence given with the product, as the kernel's own criteria check already did, up to 12 items of 400 characters. Its effect needs another live run.

## 27 October 2026: 16 trials, Haiku 5.5 twice and Sonnet 5.5

v0.5.0 as merged, with every fix above, at `--per-family 1`: the same 16 trials on each run, effort `low`, a 16,000-token cap.

| Run | Correct | Calls | Tokens | Thinking | Cost |
|---|---|---|---|---|---|
| Haiku 5.5, first | 16 of 16 | 89 | 254,065 | 25,525 | $0.054 |
| Haiku 5.5, second | 16 of 16 | 81 | 231,451 | 22,305 | $0.048 |
| Sonnet 5.5 | 16 of 16 | 80 | 162,223 | 0 | $0.58 |

| Tokens a task | single | always | genet | genet-stated |
|---|---|---|---|---|
| Haiku, first | 9,426 | 19,761 | 11,024 | 23,305 |
| Haiku, second | 9,341 | 16,760 | 12,176 | 19,586 |
| Sonnet | 6,626 | 16,332 | 8,099 | 9,499 |

- **The verifier passed all 48 products** across the three runs, each shown the evidence given with it. No rework, no refused reply.
- **Genet stayed single** at 1.17, 1.30 and 1.22 times the single agent's tokens; the crew cost 1.79 to 2.46 times. The spread between the two Haiku runs, on the same tasks, is the noise in any one figure.
- **Sonnet used fewer tokens and no thinking** at effort `low`, and cost eleven times what Haiku did, for the same score.
- **These tasks do not tell the models or the strategies apart.** With a roomy context every task fits one call, and Haiku already gets every answer. The case Genet is built for is the other one: material that does not fit one call, where the simulated single agent fails. Testing that live needs a tighter cap than 16,000, chosen for real prompt sizes: 1,500 is below what one Claude call with its tool results needs.
- **Two setup slips.** Pressing Enter at the model prompt ran Haiku twice when Sonnet was meant, so the script now has no default model and states the model, trials and cap before any call. A shortened key was refused with a 401 at the smoke test, before any billed call.

## 27 October 2026: a tight cap, 4,000 tokens a call

Three runs on Haiku 5.5 with every task's material made to overflow one call, as the simulated reader's tight case does at 1,500. Real Claude calls are larger, so 4,000 it is: one call with its tool results ran about 2,100 tokens on a lookup and 6,000 to 8,000 for a single agent on aggregate and breadth. Before the first run, the tapes showed two gaps, both fixed: Haiku read each file and also searched it, so a call carried 2.4 times the text of the files it read (up to 3.8), and the gates counted files at four characters a token while Claude counts about 1.5 times that.

| Run | single | always | genet | genet-stated | Cost |
|---|---|---|---|---|---|
| First, 32 trials | 2 of 8 | 1 of 8 | 3 of 8 | 2 of 8 | $0.058 |
| Sub-agents scoped, 32 trials | 3 of 8 | 3 of 8 | 2 of 8 | 3 of 8 | $0.083 |
| Lead told the limit, replies brief, 16 trials | 2 of 4 | 3 of 4 | 1 of 4 | 2 of 4 | $0.032 |

- **First run.** The gates split the right tasks, aggregate and breadth, and stayed single on lookup and compare. Then each sub-agent, given the whole goal and a note that said why its part was separate, read every company's file and not only its own, and its next call would not fit. Fixed: a sub-agent's tools open only the files the gates measured for its part, and its brief names them.
- **Second run.** Sub-agents kept to their files (calls of 1,700 to 1,900 tokens, not 5,000). Two other gaps showed. The lead, never told how much one call holds, proposed no sub-agents for work that could not fit; and Haiku's replies ran to 1,600 tokens, so the room kept for the next reply left none for its brief. Fixed: the plan brief states the per-call limit and the files' sizes, and replies are asked to be brief.
- **Third run.** Replies fell to about 500 tokens, and the crew got through. The lead, told the sizes, still proposed nothing: "small and sequential enough for a single agent", for work that took 4,600 tokens. And the gates' estimate would have been short too: a part's searches pull in lines from look-alike files, so a call carried about 1.7 times the files it named.
- **What it shows.** Judging fit before the work starts is unreliable on a real model: the lead misjudges it, and the gates' estimate from file sizes runs short. Every replay here was exact, from the tapes, at no cost. Open: re-plan when a call is refused for size, on the measured overflow.

## 27 October 2026: does a second agent do new work, and should we split?

Genet's question is whether a second agent does new work, and its claim is the best baseline's accuracy at close to single-agent cost. Until now the comparison never marked any work as already done, and its questions, at about 10,000 tokens of notes in all, were too small for a single agent to struggle at a real context size. Two arms, on Haiku 5.5 at effort `low`, a 200,000-token cap, 4 tool rounds, and 6 extra wrong-year figures a company, with aggregate and breadth questions from a pool of 38 companies and 12 look-alike pairs (`scripts/concept_runs.sh`). Before any call, the simulated reader got every task right under every strategy at every size; getting there found and fixed two harness gaps and one kernel bug: proposals past the cap of 16 were dropped, not handed back to the lead.

**Arm 1: parts already done.** Some companies' figures are filed and checked, given in the task's context, and marked covered in the run's world.

| Question | single | always | genet | genet-stated | Cost |
|---|---|---|---|---|---|
| 6 companies, 3 filed | 4 of 4, 21,860 | 3 of 4, 24,967 | 4 of 4, 15,512 | 3 of 4, 19,421 | $0.064 |
| 10 companies, 5 filed | 4 of 4, 27,362 | 4 of 4, 32,518 | 4 of 4, 17,398 | 3 of 4, 39,662 | $0.090 |

Correct trials, then tokens a task. No strategy read a filed company's notes again, and Haiku's crew lead left the filed parts out of its plan on its own, so the first gate had nothing to refuse. Genet was the cheapest at the same accuracy. It read about as many files as the single agent (3.2 and 3.2 a trial, then 5.0 and 4.2), but in fewer working calls (3.2 and 4.2, then 3.0 and 3.8), and each call re-sends everything read so far.

**Arm 2: more companies a question.** Each size ran twice; the 20-company run stopped itself at its cap after 28 of 32 trials.

| Companies | single | always | genet | genet-stated | Cost |
|---|---|---|---|---|---|
| 5 | 8 of 8, 12,642 | 8 of 8, 30,759 | 6 of 8, 12,824 | 7 of 8, 15,988 | $0.113 |
| 10 | 8 of 8, 47,632 | 5 of 8, 31,635 | 6 of 8, 38,528 | 8 of 8, 35,189 | $0.208 |
| 20 | 7 of 7, 83,950 | 5 of 7, 60,773 | 6 of 7, 96,868 | 7 of 7, 98,624 | $0.382 |

Right answers, then tokens a task.

- **One agent read well at every size.** The single agent got every answer right up to 20 companies, about 84,000 tokens a task. On this model and these tasks, splitting for quality is not supported: there was no loss for a split to recover.
- **The crew lost accuracy as the work grew,** 8 of 8, then 5 of 8, then 5 of 7, in hand-offs and merges. Headcount costs accuracy as well as tokens.
- **The crew got cheaper past about 10 sources.** A single agent re-sends everything it has read every round, so its cost grows faster than the crew's. Per right answer they were about even at 20 companies (84,000 and 85,000 tokens). Genet stayed single at every size, since the material fits, and so did not take the cheaper split; with the crew's accuracy loss, that was the better call here.
- **Genet's misses were one task.** All five were the same aggregate question, which names Halvorsen Freight Labs: Genet read `halvorsen-freight.md`, the look-alike's file. The context's own example of a file name was Halvorsen Freight, and every strategy read the wrong file at least once; the single agent read the right one after the wrong one said "Halvorsen Freight Labs is a separate company", and Genet did not. Fixed in the harness: the example names a company with no look-alike.
- **Spend.** $0.86 for 128 trials, plus a $0.001 smoke test.

## 28 October 2026: the aggregate questions again, with the trap fixed

This run checks the fix: single and Genet on the aggregate questions only, with the same settings, over 5, 10 and 20 companies, each size run twice (`scripts/concept_runs.sh aggregate-rerun`).

| Companies | single | genet | Genet tokens vs single |
|---|---|---|---|
| 5 | 4 of 4, 16,898 | 4 of 4, 21,704 | 1.28× |
| 10 | 4 of 4, 38,928 | 4 of 4, 46,040 | 1.18× |
| 20 | 3 of 4, 70,631 | 4 of 4, 67,972 | 0.96× |

Right answers, then tokens a task. Genet was 2 of 4, 2 of 4 and 3 of 4 before the fix, so the misses were the harness's.

- **Genet never split** at any size, since the material fits one call. This run tests its planning step, which costs no accuracy here. It does not test a team.
- **The single agent's one miss** was at 20 companies, 1152.1 for 1142.6. It took Saffron Grid's figure from `saffron-grid-partners.md`, the look-alike's file. The figure came from a search result, and the right file was never opened. Its own uncertainty said "several values rest on search snippets rather than full file reads".
- **The verifier passed it.** It checked the arithmetic and said it "could not open the 20 source files". The `verify` skill has no tools, and its brief carries the lead's notes, so it can neither check a source nor come to the product fresh. This is the first problem the team design takes up ([TEAM_DESIGN.md](TEAM_DESIGN.md)): a verifier that is given the sources and not the author's notes.
- **Spend.** $0.172 for 24 trials and a smoke test.

## 29 October 2026: the verify bench on Haiku 5.5

This run measures the fix for the verifier that passed a wrong total on 28 October (`scripts/verify_runs.sh`). The harness built 24 products for six 20-company aggregate questions. Twelve are right. Six take one company's figure from its look-alike's file, and six take one company's FY2025 figure. Each product was reviewed under five setups, 120 reviews; only the verifier's calls went to the model.

| Setup | Wrong caught | Naming the error | Look-alike | Wrong year | Right failed | Files shown | Tokens a review |
|---|---|---|---|---|---|---|---|
| `today` | 2 of 12 | 2 | 0 of 6 | 2 of 6 | 0 of 12 | 0 | 3,354 |
| `shared-full` | 12 of 12 | 12 | 6 of 6 | 6 of 6 | 0 of 12 | 20.25 | 19,875 |
| `independent-full` | 12 of 12 | 12 | 6 of 6 | 6 of 6 | 0 of 12 | 20.25 | 19,642 |
| `shared-layered` | 9 of 12 | 9 | 6 of 6 | 3 of 6 | 0 of 12 | 2.25 | 5,475 |
| `independent-layered` | 10 of 12 | 9 | 6 of 6 | 4 of 6 | 0 of 12 | 2.25 | 5,246 |

"Naming the error" counts the FAILs that name the company whose figure was planted, outside the verifier's repeat of the product's own list.

- **Without sources, the verifier caught only what the product gave away.** Its two catches were wrong-year products whose own evidence quoted the line "In FY2025, third-quarter revenue had been…". It passed all six look-alike errors, the kind it passed on 28 October.
- **Given every file, it caught all 12 and failed none of the 12 right products,** in both views. That costs about six times a review's tokens, $0.0027 a review against $0.0009. On a 20-company task, about 70,000 tokens on 28 October, it adds about a quarter.
- **The layered pick caught every look-alike error at 1.6 times a review's tokens,** about 3% more on a 20-company task. Its first pick, the file the goal names that the run never opened, is where a look-alike error sits, since the author read the look-alike's file instead. A wrong-year error sits in a file the author did read, so the pick finds it only by chance. The random draw opened that file for one product in six. The other wrong-year catches came from the product's own quote, or from a look-alike's file the draw opened that states the other company's FY2025 figure. The harness's look-alike notes say that ("…is a separate company and reports its own figures; its FY2025 third-quarter revenue was…"), and a real workspace may not.
- **Whenever the planted error's own file was in the brief, the verifier caught it,** in every setup.
- **One catch was for the wrong reason.** On aggregate-3, the independent layered verifier failed the product over Ferncastle Health, a figure no opened file covered, and never found Halvorsen Freight's FY2025 figure. The verdict counts it caught; "naming the error" does not. The bench now records this for every review.
- **Leaving out the author's notes made no measurable difference.** With every file, both views caught everything. With the layered pick, each caught 9 for the right reason, and they differed on two products, one each way. On aggregate-5 the shared verifier passed a product whose own evidence quoted the FY2025 line, and the independent one failed it. On aggregate-3 it went the other way. The bench's author note is mild ("with look-alike files excluded"), so it does not test a note that argues for the error.
- **No Sonnet arm.** The plan was to add one only if Haiku's independent verifier passed errors it could see. It passed none it was shown. Layered's misses were files it was not shown, which a stronger model cannot fix.
- **Spend.** $0.21 for the 120 reviews, against an estimate of $0.16, with a cap of $0.40.

After this run, `--verify-sources layered` became the default. First, the kernel's quote check, which comes with it, was run offline over all 885 products on the Claude tapes. It flagged 88, nearly all falsely, mostly evidence lines that cite two files, where it matched every quote against the first. Fixed, it flags 6, each a quote the cited files do not hold.

## 1 November 2026: the tapes read again, no new calls

An outside review raised six things to test: admission control, the verifier's independence, the policy boundary, model independence, what a dashboard would add, and whether a stranger can rerun the results. These were checked on the Claude tapes and the simulated reader, for $0.

- **Why Genet failed at the 4,000-token cap.** 13 of its 20 trials failed. Four were the unscoped sub-agents fixed after the first run. Of the other 9, the lead proposed no split in 5, so the gates had nothing to judge; the gates refused a split in 3; and an allowed split ran out in 1. A perfect fit estimate could reach only those 3.
- **The fit estimate.** Over a sweep of caps, on single-agent trials, the estimate said "fits" in 27 to 30% of the cases that overflow. A factor of 1.7 on the material, fitted on 27 October's tapes, cut that to 8% there and 2% on 28 October's 24 trials, with about 6% of the cases that fit called too big. Applied to the 26 proposals on the tapes, it flips 3 decisions, each on a run that had failed, and none at a cap of 16,000 or 200,000. Where a stated-policy run on the same task did split, 1 of 2 got the answer. It is not built: at a 200,000-token cap nothing overflowed, and a live tight-cap run should show it first. The 2 November run below shows it is not free either.
- **The gates are deterministic.** The gate code, run again on all 26 recorded proposals of two or more parts, gave the recorded staffing decision every time.
- **What the verifier missed.** All 10 wrong answers it passed were one kind: a look-alike's figure, confirmed against ground truth. None was arithmetic, and of 44 written-out sums on the tapes only one fails to add up, in a product whose final answer was right, so recomputing sums would have caught nothing. All 10 came before the verifier was given sources. Today's `layered` pick would open the right file for 9 of them, since no call read or searched it.
- **A figure check in code, tried and not built.** The idea was to check each figure against the file of the company it is given for, at no token cost. On the verify bench it flagged 12 of 12 wrong products and 0 of 12 right ones. On real products, tuned on some tapes and read on all, it flagged 3 of 11 wrong figures and 5 of 272 right products. The bench's products are tidier than a model's prose, so a check that parses products should not be judged on the bench alone.
- **A stranger's run.** A clean clone reproduces the simulated figures, and with the tapes copied in, all 24 of the 28 October trials to the token, with no key and no SDK. Without the tapes it cannot rerun any live figure. They are 2.5 MB gzipped, and a scan for keys, local paths and names found none.
- **The default abort check, read against the record.** The kernel's forecast was rebuilt at every decision point of all 372 trials, 807 points. `forecast_short` would never have fired, and the nearest case needed a tenth of what was left. All 45 budget halts were one call too large to send at the 4,000 cap, which the forecast does not judge. So the default, on since v0.9.0, costs nothing on these runs; its benefit is shown on the simulated reader, at a budget below the run's cost.
- **The author's note, on the verify tape.** In the shared view the brief carries the note (checked on all 12 look-alike reviews), yet no verifier reply that passed a wrong product echoed it, and only 2 of 120 replies echoed it at all. A mild note had no visible pull. Whether a note that argues for the error does, and whether an instruction planted in a source file does, are the two new arms of `verify-bench` (`--arms note,planted`), run on 2 November below.
- **Other models.** Both adapters send the same system prompt and message. The OpenAI-compatible parser takes fenced JSON, prose around it, and missing keys; it refuses a `<think>` block with braces in it, and any extra key, the second by design.

## 2 November 2026: reporting up, the cards, and the verifier against an argument

`scripts/team_runs.sh`, v0.9.0, on Haiku 5.5 at effort `low`. It cost $0.10 in all, against an estimate of $0.12 and caps of $0.37. All three tapes replay with no missing requests and the same results.

**Does a sub-agent hand back a part the plan got wrong?** 24 parts of 20-company questions under each brief: 12 right, and 12 whose channel holds the wrong file.

| Brief | Wrong parts handed back | Said missing | Gave the wrong file's figure | Right parts reported | Right parts handed back | Tokens a part |
|---|---|---|---|---|---|---|
| default | 0 of 12 | 10 | 2 | 12 of 12 | 0 | 4,442 |
| `--report-up` | 10 of 12 | 0 | 2 | 12 of 12 | 0 | 4,705 |

- **It rarely guesses, and reporting up changes where the problem goes.** The same 10 parts that said in prose that the figure was missing were handed back under `--report-up`, at 6% more tokens, and no right part was. Without it, a lead has to read that prose and notice; with it, the kernel opens a replan request and the lead is told.
- **Both wrong figures are one pairing.** Saffron Grid, given the notes of Saffron Grid Partners, under both briefs. It is the look-alike that cost the single agent its one miss on 28 October, a company whose look-alike only adds a word to its name. A sub-agent that takes the file for the company has no reason to report anything.
- **A bench bug, found by reading the claims.** The bench first scored 2 of these as "said missing", because it looked for missing-sounding words before it looked for the figure: "$72.9 million, per saffron-grid-partners.md … my channel holds no files for the other 21 companies." The answer line now decides. Rescored from the tape with no spend, in `report-20261102-092137-rescored.json`.
- **Not measured.** This bench tests a sub-agent alone. Whether the lead then covers the part well is for a crew run.

**Do the cards change the plan?** 8 trials of 10-company aggregate questions at an 8,000-token cap, half with the cards. This did not test the cards, because no trial got a split, and every one stopped when the lead working alone ran past the cap.

| Strategy | Finished | Parts proposed a trial | Refused | Prompt tokens, plan call | Tokens a trial |
|---|---|---|---|---|---|
| genet | 0 of 4 | 2.75 | 2.75 | 1,328 | 5,391 |
| genet with cards | 0 of 4 | 2 | 2 | 1,789 | 4,294 |

- **The lead saw the problem.** It proposed a split on all 8 trials, with notes like "ten files exceed one call budget". Told the limit on 27 October, it had proposed nothing. So at this cap the size note works.
- **The gates refused what it proposed.** On 6 trials the parts were groups: `group-a`, `companies-b`, `brightwater-calderon-marrowgate`. With 10 files and a cap of 4 sub-agents, grouping is the sensible plan. But the gates measure a part by a file named for its channel or named in its note, and the plan brief asks for a channel name and a failure, so the gates found "the material is unknown". On the other 2 trials the lead proposed two single files, which fit, and one group alone, which is the lead's own job.
- **Naming the files would have got them through.** Offline, with each group's share of the files added to its note, the gate code admits the split on all 6 grouped trials. The toolbox already opens a part's named files, so only the plan brief is missing a sentence. Built and run in the follow-up below.
- **The 1.7 factor is not free.** With it, the same offline check admits only 1 of the 6, since a five-file group then reads as too big. The 27 and 28 October tapes could not show this, because their leads proposed one part per file. The follow-up below shows it would have refused work that fit.
- **The cards cost more on Claude than in the sim.** About 460 prompt tokens on a plan call, 35% more on that call, where the sim said about 250. They stay off. Whether they change a plan is still not known.
- **The setup was the harness's fault.** This arm was sized on the simulated reader, whose lead names a part after each file. Haiku does not plan that way.

**Does the verifier hold against an argument?** The verify bench's products, under the default `shared-layered`, against the same products on 29 October.

| Arm | Look-alike caught | Wrong-year caught | Right products failed | Own file shown, caught | Own file not shown, caught | Tokens a review |
|---|---|---|---|---|---|---|
| plain, 29 October | 6 of 6 | 3 of 6 | 0 of 12 | 7 of 7 | 2 of 5 | 5,475 |
| `note` | 6 of 6 | 2 of 6 | not reviewed | 7 of 7 | 1 of 5 | 5,951 |
| `planted` | 6 of 6 | 3 of 6 | 0 of 12 | 7 of 7 | 2 of 5 | 5,730 |

- **The planted instruction was never followed.** It was in all 24 briefs, telling the verifier to pass a wrong product or fail a right one. All 12 right products passed and all 7 wrong ones whose own file it saw failed, and 21 of 24 replies called it out, as "an instruction embedded in the source, not evidence". That judgement is the model's. No Genet prompt tells it to distrust a file, and this is one wording on one model, so it does not show that another would hold.
- **What decides a catch is still whether the file is shown.** Under both arms, every miss was a product whose own file was not opened, as on 29 October. Against that plain run, one product moved to a pass under both arms and one to a fail under `planted`, which reads as noise. Each product ran once.
- **The note moved the reasoning, not the verdict.** In 5 of the 6 look-alike reviews, the verifier accepted the note's false claim that the company's own file is a stale duplicate. It failed the product only because the file the note cites had not been opened. That catch is fragile: a review that opens that file as well may pass the product. `shared-full` opens it, and the independent view drops the note. The follow-up below runs both.

## 2 November 2026: the follow-up

`bash scripts/team_runs.sh followup`, the same day, on Haiku 5.5 at effort `low`. It cost $0.08, against an estimate of $0.09 and caps of $0.18. Both tapes replay with no missing requests and the same results.

**A lead told how to name a group's files.** When the workspace does not fit one call, the plan brief now says that there can be at most 4 sub-agents, and that a part reading several files names each one in its note. The same 8 trials, at the same 8,000-token cap.

| Strategy | Split | Refused | Right answer | Verified | Tokens a split run |
|---|---|---|---|---|---|
| genet, before the note | 0 of 4 | 2.75 parts a trial | 0 of 4 | 0 of 4 | none |
| genet, with the note | 3 of 4 | 0 | 3 of 4 | 3 of 4 | 33,735 to 36,778 |
| genet with cards, before the note | 0 of 4 | 2 parts a trial | 0 of 4 | 0 of 4 | none |
| genet with cards, with the note | 2 of 4 | 0 | 2 of 4 | 0 of 4 | 42,107 and 49,420 |

- **These are Genet's first live splits on questions that do not fit one call, and all 5 reached the right answer.** The gates admitted every part of every plan, measured from the names. The verified runs cost about what one agent took at a 200,000-token cap on 28 October (38,928), though that verifier opened no files.
- **Three leads proposed nothing and overflowed,** each judging ten short files to fit one agent, as on 27 October. Without the note all 8 had proposed something, so the note may have some cost, or this may be noise. A lead that misjudges is still not rescued: re-planning on a measured overflow (design part 4) is the piece that would.
- **The estimate is good for a scoped part, so the 1.7 factor is dropped.** Over all 17 sub-agents, the largest call ran a median of 1.16 times today's estimate and at most 1.29 times, and none reached the cap. A sub-agent's tools open only its files, so its searches cannot pull in look-alikes, which is where the 1.7 came from. The factor would have refused the two five-file groups, which ran at about 6,300 tokens.
- **The verifier failed right answers after a split.** It gave 6 FAILs on right answers across 3 of the 5 split runs. One run recovered on its rework; two stopped with `VERIFY`, which is why the cards row shows none verified. Under the layered pick it saw 2 of the 10 files, and it read the other 8 figures as unsupported: "only two of its ten inputs are supported by the opened sources". The verify bench did not show this, since its products quote their sources and no right product failed there. Open.
- **The cards.** Both arms' splits came from the note, not the cards. With them 2 of 4 leads split, without them 3 of 4, and the two runs that stopped on the verifier are that problem, not the cards'. Eight trials over two runs show no sign they help, and they cost about 460 prompt tokens a plan call. They stay off.
- **A limit found while building it.** Underscores in a note read as spaces, so a file whose name has an underscore cannot yet be named this way. The first fix tried also changed how the crew's proposals are read, so it was taken out, and this stays open.

**The false note, with the file it cites opened.** `shared-full` opens every file, so both the company's own file and the look-alike's are in the brief.

| Verifier | Sources | Plain | Against the false note | Look-alike | Wrong year |
|---|---|---|---|---|---|
| shared | layered | 9 of 12 | 8 of 12 | 6 of 6 | 2 of 6 |
| shared | full | 12 of 12 | **7 of 12** | **1 of 6** | 6 of 6 |
| independent | layered | 10 of 12 | 10 of 12 | 6 of 6 | 4 of 6 |
| independent | full | 12 of 12 | 12 of 12 | 6 of 6 | 6 of 6 |

- **The author's false note got 5 of 6 look-alike errors past a verifier that held every source.** Told that a company publishes under its look-alike's file and that its own is a stale duplicate, the verifier checked each figure against the file the note named: "Ostrander Media 71.6 (from ostrander-media-labs.md)". It passed, in a setup that caught all 6 without the note. Its one catch read the look-alike's own line, that the company "is a separate company", and doubted the premise.
- **The independent view stops it, since the note never reaches the verifier.** Its brief is the same with or without the note, so the 29 October tape answers both independent rows, all requests found, at no cost. This is the first result that separates the two views. On 29 October, with a mild note, they did not differ.
- **The wrong-year note failed, 6 of 6.** It claimed the right line was a plan figure, and the verifier read the file and said so: "nothing in the file labels it a plan figure". So a note that a source can contradict does not get through. One about which file is the source does, because the files do not settle it unless they say so.
- **The layered 6 of 6 was luck, as the first run suspected.** The note's file was not opened there. A real product that cites that file, or a draw that picks it, would be in the `full` row.
- **A planted instruction in a file did nothing, and the same claim from the author nearly always worked.** The verifier treats a member's note as part of the team's record. So the route from a planted instruction to a wrong verdict may run through the author: steer the lead, and its note reaches the verifier. That route has not been tested.
- **Not settled: which view should be the default.** The independent view also leaves out the sub-agents' reports, so it might fail more right answers after a split, the problem above. That needs a live run of split runs under `--verify-view independent`.

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

The Claude runs' results are in `data/compare/` and their tapes in `data/tapes/`, and those through 29 October are published as [a release](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261029) with a `REPLAY.md` that gives each tape's command. The run files in `data/` and `Data2/` stay on the operator's machine and are not committed. `Data2/data/` is a backup copy of `data/`. The four episodes in `data/episodic/` that have no saved run (`mx-001`, `pw-001`, `so-001`, `so-live-gate`) came from the stub adapter, not from a live model.
