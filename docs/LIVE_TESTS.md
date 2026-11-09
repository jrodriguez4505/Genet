# Live test log

Genet's runs against real models: the first comparison pilot on Claude, two reruns with fixes, 16-trial runs on Haiku 5.5 and Sonnet 5.5, three runs at a tight cap, and the concept experiments (27 October 2026), the aggregate rerun and the verify bench (28 and 29 October), reporting up, the cards, the verifier arms, three follow-ups, a side-by-side run, a told crew and a check of the fixes (2 November), a check of a sub-agent's room, two benches and the verifier on real merges (3 November), the verifier's rule on new questions (3 November), two benches and a whole run (4 November), its rerun and a test of one more verifier sentence (5 and 6 November), a narrower sentence and a check in code (7 November), how many agents a task needs on three models (7 and 8 November), a head-to-head with CrewAI on public documents (9 November), and 13 runs of v0.1 on xAI's endpoint (31 August and 1 September 2026). The tapes and results are published as GitHub releases: those of 3 to 6 November as [tapes-20261106](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261106), 3 November's earlier runs as [tapes-20261103](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261103), 2 November's as [tapes-20261102](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261102), and those through 29 October as [tapes-20261029](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261029), with a replay command for each; the run files in `data/` stay on the operator's machine.

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
- **Three leads proposed nothing and overflowed,** each judging ten short files to fit one agent, as on 27 October. Without the note all 8 had proposed something. The next run makes this harder to call noise. A lead that misjudges is still not rescued: re-planning on a measured overflow (design part 4) is the piece that would.
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
- **Not settled: which view should be the default.** The independent view also leaves out the sub-agents' reports, so it might fail more right answers after a split, the problem above. The next run tests it.

## 2 November 2026: split runs under the independent view

`bash scripts/team_runs.sh independent`, the same day, on Haiku 5.5 at effort `low`: genet without the cards, the 10-file questions twice each at an 8,000-token cap, with `--verify-view independent`. It cost $0.03, against an estimate of $0.05 and a cap of $0.10. The tape replays with no missing requests and the same results. Before the run, the sim confirmed that after a split the shared view shows the verifier both groups' reports and the independent view neither, with the same files opened.

| View | Trials | Split | Right answer | A FAIL on a right answer | Stopped on the verifier | Verified |
|---|---|---|---|---|---|---|
| shared, with and without the cards | 8 | 5 | 5 of 5 | 3 of 5 runs, 6 FAILs | 2 of 5 | 3 of 5 |
| independent, without the cards | 8 | 3 | 3 of 3 | 1 of 3 runs, 2 FAILs | 1 of 3 | 2 of 3 |

- **The independent view did not fail more right answers.** Three split runs cannot show it is better, but they show no sign that it is worse, which was the question. Together with the false note (12 of 12 against 7 of 12), the plain bench (never fewer catches, no right product failed) and slightly fewer tokens, the case for it is the stronger one.
- **So the view is not what causes the false failures.** The same reason appears under both: the product rests on the groups' subtotals, the layered pick opens 2 of the 10 files, and the verifier reads the other 8 as unsupported. Sometimes it fails the product for that, and sometimes it passes and says so: "Only Cobalt Ridge and Everholt were opened … the other eight company figures … are unverified". So a pass after a split checks 2 of 10 files, under either view, and means less than the word suggests.
- **All 8 split runs on this cap have now reached the right answer.** The gates admitted every part of every plan.
- **The leads are now the limit.** Only 3 of 8 proposed a split. With the group note that makes 8 of 16, where all 8 proposed something before it, so the note may be putting leads off. This is one set of four questions, so it is a sign and not a measure. The other leads misjudged the size: "Ten files of about 1,000 tokens each fit one agent's 8,000-token budget". The size note gives the range of file sizes across the whole workspace and leaves the lead to add up the part it needs. A lead that misjudges then overflows, and nothing rescues it.

## 2 November 2026: the lead told what the files come to

`bash scripts/team_runs.sh size`, the same day, on Haiku 5.5 at effort `low`. It cost $0.05, against an estimate of $0.05 and a cap of $0.10. The tape replays with no missing requests and the same results.

After the last run the independent view became the default, and the size note gained one sentence, only when the files the goal names do not fit one call: "The 10 files the goal names come to about 8,681 tokens, and a single agent's later calls carry everything it has read, so with this brief they do not fit one call." The same 8 trials as the run before it.

| The lead is told | Proposed | Split | Right answer | Verified | A FAIL on a right answer | Tokens a split run |
|---|---|---|---|---|---|---|
| the sizes only | 8 of 8 | 0 of 8 | 0 of 8 | 0 of 8 | none to fail | none |
| the sizes, and how to name a group (two runs) | 8 of 16 | 8 of 16 | 8 of 16 | 5 of 16 | 4 of 8 runs | 29,361 to 49,420 |
| the sizes, how to name a group, and the total | 8 of 8 | 7 of 8 | 7 of 8 | **6 of 8** | 1 of 7 runs | 26,067 to 38,802 |

- **Doing the sum for the lead worked.** All 8 proposed a split, where 3 of 8 had in the same setup just before. It is a fact the kernel measures, not advice, and the gates still judge the proposal.
- **Every one of the 15 split runs on this cap has reached the right answer.** The verified runs here cost about what one agent took at a 200,000-token cap on 28 October (38,928), with the verifier opening 2 files as well. This is one family of four questions at a cap chosen to overflow. At 200,000 tokens nothing overflowed, and a single agent got these answers, so it does not show that a split beats one agent where one agent can do the work.
- **The last failure was a guessed file name.** The lead wrote `cobalt ridge.md` and `ostrander media labs.md`, guessing from the company's name. One group then named no file the workspace holds, so the whole plan read as unmeasured and was refused, and the lead overflowed alone. Open. The brief could list the goal's files, but that would also hand it the look-alike distinction this suite tests.
- **False failures fell, and the independent view is not the cause of them.** Under it, 2 of 10 split runs have had a FAIL on a right answer, against 3 of 5 under the shared view. This run's one was a different complaint, that a figure's line names no year. The sample is small and the runs differ, so this does not show the view reduces them. After a split the layered pick still opens 2 of 10 files, so a pass checks little under either view.

## 2 November 2026: single, crew and Genet side by side

`bash scripts/team_runs.sh wide`, on Haiku 5.5 at effort `low`, at an 8,000-token cap: 90 trials, 6 questions of each of the four types over 10 companies, then 3 each of aggregate and breadth over 20. It cost $0.33, against an estimate of about $0.50 and caps of $0.75.

| Questions, verified answers | Single | Crew | Genet | Genet's leads that split |
|---|---|---|---|---|
| Lookup and compare, which fit one call | 12 of 12 | 7 of 12 | 12 of 12 | 0 of 12 |
| Aggregate and breadth, 10 companies | 0 of 12 | 4 of 12 | 8 of 12 | 10 of 12 |
| Aggregate and breadth, 20 companies | 0 of 6 | 0 of 6 | 5 of 6 | 6 of 6 |

| Tokens a task | Single | Crew | Genet |
|---|---|---|---|
| Lookup and compare | 9,168 | 16,844 | 10,422 (1.14× single) |
| Aggregate and breadth, 10 companies | 3,456, stopping early | 30,856 | 28,786 |
| Aggregate and breadth, 20 companies | 1,959, stopping early | 16,030, stopping early | 43,107 |

- **The leads and the gates did what they are for.** On all 12 questions that fit one call, no lead proposed a split, and Genet matched the single agent at 1.14 times its tokens. On all 18 that do not, every lead proposed one, and the gates admitted 16 of those plans. The size note is doing this: on these questions the kernel told the lead what its files come to, and on the others it had nothing to say.
- **The single agent cannot do this work at this cap.** It ran out on every aggregate and breadth question. One gave the right answer before it stopped, unverified. That is the cap, not the model: at 200,000 tokens a single agent got these answers on 28 October.
- **On the small questions the crew lost by itself.** It split one-file lookups into workers it did not need, for example a `verify` worker with no tools and a `draft` worker, and its leads then answered `UNKNOWN` for figures its own workers could read. Genet's gates refuse those parts. This part of the comparison is fair.
- **On the big questions the comparison is not yet fair.** The crew's plan brief has no size note and no word on naming a group's files, so a crew lead gets no warning that the files will not fit, and its groups may not name them. Some did not, so their workers' tools stayed unscoped. Part of Genet's lead here is notes it was given and the crew was not. So this shows that Genet works at this cap, and not that it beats a crew told the same things. The next run tests that, and most of the lead goes.
- **No wrong answer got through.** In all 90 trials, no finished run gave a wrong answer. But very few wrong answers were produced for the verifier to catch, and after a split it opens 2 of the files, so this says little about what it would catch.
- **Genet's 5 misses in 30.** Two plans were refused because the lead guessed files' names (`Quillon Bio.md`), so a group named no file the workspace holds. One group overflowed at 20 companies. Two right answers were stopped by the verifier.
- **The false failures continue.** Under the independent view, 6 of 26 split runs have now had a FAIL on a right answer, and 4 stopped on it. After all of today's runs, 30 of 31 split runs reached the right answer; the other is that overflow.
- **The simulated reader got this one wrong.** At 20 companies it fails every Genet trial, because its lead plans one part per file: the gates admit 4, and it cannot then fit the other 16 in its merge call. Haiku grouped the files, and got 5 of 6. A lead that plans by the file at this size would still hit that, so the gates may need to count what they leave for the lead to cover.
- **Not every trial replays to the token.** 81 of the 90 do. The other 9 stopped during their sub-agents, 8 of the crew's and 1 of Genet's. Sub-agents run in parallel, and when one stops a run, how many calls the others had finished depends on timing, so calls and tokens differ on replay. All 9 failed both when recorded and on replay, and 8 with the same code. This is the first tape to show it, since no earlier one that still replays has a run stopping there. The next run shows a sharper case.

## 2 November 2026: a crew told the same things

`bash scripts/team_runs.sh crew`, on Haiku 5.5 at effort `low`. It cost $0.19, against an estimate of $0.20 and caps of $0.37. The new strategy `always-told` is the crew with the same size notes as Genet's lead, in its own brief's words, and still no gates. It answers the same 30 questions as the side-by-side run. It ran all four question types at 10 companies, because naming fewer changes which questions the seeded suite draws.

| Verified answers, 8,000-token cap | Single | Crew | Told crew | Genet |
|---|---|---|---|---|
| Lookup and compare, which fit one call | 12 of 12 | 7 of 12 | 9 of 12 | **12 of 12** |
| Aggregate and breadth, 10 companies | 0 of 12 | 4 of 12 | **9 of 12** | 8 of 12 |
| Aggregate and breadth, 20 companies | 0 of 6 | 0 of 6 | 4 of 6 | **5 of 6** |
| All 30 | 12 | 11 | 22 | **25** |

| Tokens a task | Single | Crew | Told crew | Genet |
|---|---|---|---|---|
| Lookup and compare | 9,168 | 16,844 | 16,431 | **10,423** |
| Aggregate and breadth, 10 companies | stopped early | 30,856 | 35,977 | **28,786** |
| Aggregate and breadth, 20 companies | stopped early | stopped early | 46,080 | **43,107** |

- **Most of Genet's lead on the large questions was the notes.** Told what its files come to and how to name them, the crew went from 4 of 18 verified to 13 of 18, the same as Genet. These are facts the kernel measures, so any lead could be given them. The earlier 13 against 4 says more about the notes than about the gates, and it should not be read as gates beating a crew.
- **On large work, the crew reached more right answers.** It got all 18, where Genet got 15. Genet's 3 misses are 2 plans the gates refused because a guessed file name left one group unmeasured, and 1 group that overflowed. A crew has no gate to refuse a plan, and its workers got on with the groups they could read. So the rule that one unmeasured part refuses the whole plan cost Genet right answers here, and is worth changing. The crew then lost more of its right answers to the verifier, 5 against 2, so both verified 13. Genet used 15% fewer tokens.
- **On work that fits one call, the gates are what make the difference.** No lead of Genet's proposed a split, and it got 12 of 12 at 1.14 times a single agent's tokens. Told crews still split all 12, as a crew must, and got 9 at 1.79 times. Its 3 misses were comparison questions, whose leads answered "undetermined" from their workers' two reports where a single agent read both files.
- **Over all 30, Genet verified 25 and the told crew 22, at 0.81 times the tokens.** That is one run of each trial, on one synthetic suite, one model and one cap, so the difference is a sign and not a measure.
- **Still no wrong answer got through.** No finished run gave a wrong answer in these 30 either.
- **A kernel behaviour that is not deterministic.** Replaying this tape, one crew trial that finished when recorded stopped in 1 of 3 attempts, on a call of about 6,318 tokens plus 1,691 kept for the reply, 9 over the cap. The size check keeps room for the largest reply so far in the whole run, and with sub-agents in parallel, which replies have arrived depends on timing. So near the cap, the same replies can go either way. The gates themselves are deterministic, and the other 29 trials replay exactly. Fixed in v0.9.1: a sub-agent no longer counts its siblings' replies, and this trial finished on 5 of 5 replays.

## 2 November 2026: a check of the fixes

`bash scripts/team_runs.sh fixes`, on Haiku 5.5 at effort `low`, on the 30 questions of the side-by-side run, Genet only, with two fixes: a file name counts however a model spelled it, and a part that names no real file goes to the lead while the rest of the plan stands. It cost $0.14, against an estimate of $0.17 and caps of $0.32. The third fix, that a sub-agent's room no longer depends on its siblings, was checked offline.

| Verified, then right, at an 8,000-token cap | Genet before | Genet with the fixes | Told crew |
|---|---|---|---|
| Lookup and compare | 12, 12 | 12, 12 | 9, 9 |
| Aggregate and breadth, 10 companies | 8, 10 | **10, 12** | 9, 12 |
| Aggregate and breadth, 20 companies | **5, 5** | 3, 3 | 4, 6 |
| All 30 | 25, 27 | 25, 27 | 22, 27 |

- **The totals did not move.** The fixes helped where they applied and three other stops cost the same amount. Each is one run of each trial, and the lead's plans vary from run to run, so this shows what the fixes do to a plan, not a new rate.
- **At 10 companies the fixes did what they were for.** No plan was refused, all 12 leads split, and all 12 answers were right. The 2 misses are right answers the verifier stopped.
- **At 20 companies three runs stopped, and the fixes caused none of them.** All 6 plans get the same verdict from the gates before the fixes, and the room that stopped the third is the same.
- **One lead ran its file names together.** The brief's only example is a one-word name, `orbrook.md`, so this lead wrote `cobaltridgecapital.md`, and only the 4 one-word names of 20 were found. The gates then measured about a fifth of the work and refused the plan as fitting one call. Run-together names now count. With them, that plan's 20 files are all found, and it is still refused, 43 tokens short: 4,602 for its largest group against 4,559 available.
- **One run stopped 44 tokens over the cap, on a call that would have fit.** A sub-agent's brief of about 6,036 tokens, plus 2,008 kept for the reply, against 8,000. The 2,008 was the lead's plan reply. No sub-agent's reply on the side-by-side and check tapes passed 1,793, and no sub-agent's call passed 7,268. So the size check and the gates count a figure that says little about a sub-agent. This is open.
- **One lead's groups were too big, and it had no way back.** It planned 8, 7 and 5 files. The gates were right: the largest needs about 6,539 tokens against 5,773. The lead then worked alone and overflowed on its next call. This is open.
- **A scoring bug hid a right answer.** One lead wrote `Group-c's own 'ANSWER: 239.1' is a partial subtotal and is not the combined answer. ANSWER: 1020.9`. The verifier passed it and it was right, but the scorer read from the first marker on a line, so it scored wrong. The scorer now takes the last. This changed a score after the result was seen, so both files are kept: the table uses `fixes20-20261102-151115-rescored.json`, and the original is beside it. It is the only one of 958 saved results with a second marker in its answer.
- **Still no wrong answer got through.** Once that answer is read correctly, every finished run in these 30 is right.
- **The false failures continue.** 2 of the 15 split runs that reached the right answer had a FAIL on it, and both stopped. Under the independent view that makes 8 of 41 split runs, and 6 stopped. The cause looks the same: the layered pick opens 2 of the files, and the verifier reads the rest as unsupported.

## 3 November 2026: a sub-agent's own room, and a second plan

`bash scripts/team_runs.sh second`, on Haiku 5.5 at effort `low`, on the 6 questions at 20 companies, Genet only, with two fixes: a sub-agent keeps room for a sub-agent's reply, and a plan with a part too big gets a second try. It cost $0.06 with its smoke test, against an estimate of $0.06 and a cap of $0.10.

| 20 companies, 8,000-token cap, 6 questions | Before any fix | v0.9.1 | This run | Told crew |
|---|---|---|---|---|
| Leads that split | 6 | 4 | **6** | 6 |
| Verified | 5 | 3 | 4 | 4 |
| Right | 5 | 3 | 5 | 6 |
| Stopped on size | 1 | 3 | **0** | 0 |
| Stopped by the verifier | 0 | 0 | 1 | 2 |
| Stopped on a malformed reply | 0 | 0 | 1 | 0 |

- **No run stopped on size.** Each column is one run of each question, and the leads' plans vary from run to run, so this shows what the fixes do to a plan, not a new rate.
- **The room fix changed one run.** On the code before it, the same tape stops `aggregate-3` on the size check, after 6 or 7 calls: a brief of about 6,083 plus a plan reply of 2,030. The other 5 trials replay the same on both. That trial's answer was right, and the verifier then stopped it, so this did not change the totals.
- **The second plan did not fire.** All 6 leads planned 4 groups of 5 files on the first try, and none was refused. On v0.9.1 two of the 6 plans were refused. So no real lead has written a second plan yet, and whether it would fit is not shown. Offline, the plans refused on the tapes do reach it, and its brief says what was measured: `group-a (8 files, ~6,539 tokens), group-b (7 files, ~6,168 tokens), group-c (5 files, ~4,110 tokens)`.
- **1,500 tokens held, with little to spare.** After reading, sub-agents' replies ran to a median of 1,301 and a largest of 1,841, and 5 of 24 passed 1,500. The largest call before its reply was 6,339, and none was cut off. A reply that large on the largest call would be cut off, and its part would go back to the lead.
- **A new stop: a malformed merge.** `breadth-2`'s lead wrote the right answer twice, in replies that were not JSON: one closed a list with `}`, and the other wrote `\$`. One retry is all a reply gets, so the run stopped with no answer. The fixes did not touch this. On the tapes of 2 and 3 November 8 of 1,428 replies were not JSON as sent, and this stopped 2 of 284 trials, this one and a crew's. This is open.
- **The false failures continue, and were more common.** 4 of the 5 runs that reached the right answer had a FAIL on it. A rework passed 3, and 1 stopped. The verifier's brief has the same form as before, and it gives the same reason: the layered pick opens 2 of the 20 files, and the verifier reads the rest as unsupported. Under the independent view that makes 12 of 46 split runs, and 7 stopped.
- **Still no wrong answer got through.** Every finished run was right. The tape replays on this code with no request missing and the same results, twice.

## 3 November 2026: the second plan, and the verifier after a split

`bash scripts/team_runs.sh next`, on Haiku 5.5 at effort `low`, two benches at an 8,000-token cap. It cost $0.10 with its smoke test, against an estimate of $0.10 and caps of $0.20.

### Told why its plan was refused, does a lead write one that fits?

`plan-bench` hands the run a first plan the gates refuse, and only the lead's second planning call goes to the model. It stops at the plan, so no sub-agent worked. 6 questions at 20 companies, 3 shapes, $0.02.

| First plan's groups | Plans | Refused, so asked again | Second plan admitted | And it covers every file |
|---|---|---|---|---|
| 8, 7, 5 files | 6 | 6 | 6 | 6 |
| 10, 10 files | 6 | 6 | 6 | 6 |
| 7, 7, 6 files | 6 | 6 | 6 | 5 |

- **It fits.** All 18 second plans were admitted, and 17 were 4 groups of 5 files, the plan most leads write first. A plan cost about 3,500 tokens, about $0.001.
- **One plan left files out, and the gates admitted it.** On `breadth-3`, the lead named 15 of the 20 files, leaving out Redfern Analytics, the question's right answer. The gates measure what a part names, not what a plan leaves out. None of 78 first plans on the tapes by leads told the sizes did this, so it may belong to replanning. Files like these now go to the lead to cover in the merge.
- **What this does not show.** The first plan was the bench's, not the lead's own, and no run has yet gone on from a second plan to an answer.

### Told its sources are a sample, does the verifier stop failing right answers?

`verify-bench --arms split` reviews products shaped like a lead's merge: group subtotals, no file cited, and an uncertainty saying the lead opened no file. 6 questions at 20 companies, 36 products, each reviewed under both rules, 72 reviews, $0.08. Today's rule is `independent-layered`. `independent-told` adds that the files are a sample, and that a figure no file covers is no reason to FAIL.

| Rule | Right products failed | Errors caught, file shown | Errors caught, file not shown |
|---|---|---|---|
| Today's | 0 of 12 | 12 of 12 | 0 of 12 |
| Told it is a sample | 0 of 12 | 12 of 12 | 0 of 12 |

- **The bench did not reproduce the false failures.** Today's rule failed none of 12 clean right products. On the real merges on the tapes it failed 32 of 104 right answers. So this says nothing about whether the note stops them, and the note stays off. It does show the note did no harm to these catches.
- **On a clean product the verifier is an exact check of what it is shown.** Every error in a file it was shown was caught, naming the company. No error in a file it was not shown was. So a pass after a split, with 2 of 20 files open, says little about the other 18.
- **What real merges have that these lack, read from the tapes and not tested.** 16 of the 32 failures cite a year or quarter label, such as an `April–June` figure with no FY2026 beside it, though the file is headed FY2026. By a rough word match, products that voice a doubt of their own failed 18 of 38, against 14 of 66 for the rest. So a sub-agent's doubt may travel through the merge to the verifier. The next run tests this on the real merges.

Both tapes replay on this code with no request missing and the same results.

## 3 November 2026: the verifier on the real merges

`bash scripts/team_runs.sh merges`, on Haiku 5.5 at effort `low`. `merge-bench` takes the verifier's requests from the tapes of 2 and 3 November, every review of a product after a split under the independent view, and asks again under each rule. That is 123 reviews, 104 of right answers and 19 of wrong ones, under 4 rules, 492 calls. It then ran the built products under the two new rules, 72 reviews. It cost $0.56, against an estimate of $0.64 and caps of $1.00.

The rules add sentences after the source rule. `told` says the files are a sample, and a figure no file covers is no reason to FAIL. `headed` says a line with no year takes the year in its file's heading. `both` says both.

| Rule | Right answers failed | Failed when recorded, failed again | Passed when recorded, failed now | Wrong answers caught | Wrong answers passed |
|---|---|---|---|---|---|
| Today's | 34 of 104 | 22 of 32 | 12 of 71 | 18 of 19 | 0 |
| Told | 7 of 104 | 4 of 32 | 3 of 71 | 17 of 19 | 1 |
| Headed | 23 of 104 | 16 of 32 | 7 of 71 | 18 of 19 | 0 |
| **Both** | **3 of 104** | 3 of 32 | **0 of 71** | **18 of 19** | **0** |

- **This bench reproduced the false failures.** Today's rule failed 34 of 104, against 32 when recorded, so the comparison is fair where the clean products were not.
- **The two sentences together nearly stopped them.** Product by product, today's rule failed 31 that `both` passed, and `both` failed none that today's passed.
- **Most of it is being told the files are a sample.** That alone took failures from 34 to 7. The heading alone took them to 23. `told` alone also let one wrong answer through, on `compare-2`, where `both` did not. One wrong answer in 19 reviews cannot separate them.
- **The 3 still failed look like fair failures.** Each is a right answer on a weak product: two rest on a figure the product itself says may be a look-alike's, and one ranks "the parts checked so far", 4 of 10 companies.
- **Wrong answers were still caught.** Under `both`, 18 of 19 were caught and none passed. The other one has no verdict under any rule: at about 7,000 tokens the brief leaves too little for the reply, and it is cut off.
- **The built products agree.** Under `headed` and under `both`: none of 12 right ones failed, all 12 errors in a file shown were caught, naming the company, and none of 12 in a file not shown. So this does not make a pass check more: it only stops failures that no source supports.
- **A verdict is noisy.** Under today's rule, asked again about the same right answer, the verifier gave the same verdict 81 times of 103. So any one run's false failures are partly chance.
- **What this does not show.** The heading sentence came from reading these same merges, so `both` is tested here on the products that suggested it. It needs new questions. It is one review of each product under each rule, on one model. The 19 wrong answers are mostly a crew's, and their errors are mostly plain to see. The rule stays off until new questions confirm it.

All the tapes replay on this code with no request missing and the same results.

## 3 November 2026: the verifier's rule on new questions

`bash scripts/team_runs.sh heldout`, on Haiku 5.5 at effort `low`. Five seeds no tape had used, 101 to 105, with `both` on in every run: 24 questions at 10 companies and 6 at 20, under single, the told crew and Genet, 450 trials. Then every review after a split on those tapes was asked again under today's rule and `both`, 259 products and 518 reviews. Then the built products on seed 101, 72 reviews. It cost $2.40, against an estimate of $2.50 and a cap of $4.10, and no run reached its cap.

The bar was written at the top of the script before the run. Both parts had to hold for the rule to become the default.

| The bar | Needed | Result |
|---|---|---|
| Today's rule fails enough right answers to tell | at least 10 | 69 |
| Right answers `both` fails | at most half of today's | **6 against 69** |
| Products only today's rule fails, against only `both` | at least 3 times | **64 against 1** |
| Wrong answers only today's rule fails | at most 1 of 39 | **1** |

| Rule | Right answers failed | Failed when recorded, failed again | Passed when recorded, failed now | Wrong answers caught | Wrong answers passed |
|---|---|---|---|---|---|
| Today's | 69 of 220 | 4 of 9 | 64 of 210 | 36 of 39 | 3 |
| **Both** | **6 of 220** | 3 of 9 | **3 of 210** | **37 of 39** | **2** |

One right answer has no verdict under today's rule: its reply did not parse.

| Right answers | Single | Told crew | Genet |
|---|---|---|---|
| Lookup and compare, 10 companies, of 60 | 57 | 51 | 58 |
| Aggregate and breadth, 10 companies, of 60 | 0 | 56 | 56 |
| Aggregate and breadth, 20 companies, of 30 | 0 | 27 | 22 |
| All, of 150 | 57 | 134 | 136 |
| Verified, of 150 | 57 | 132 | 136 |
| Each seed, of 30 | 10 to 12 | 24 to 29 | 24 to 29 |
| Tokens a task | 5,833 | 28,283 | 25,561 |
| Cost per right answer | $0.0031 | $0.0064 | $0.0057 |

- **The rule cleared its bar, and the earlier result held.** Today's rule failed 31% of right answers here and 33% on seed 7. `both` failed 3% in each. Every seed shows it: 11, 16, 12, 18 and 12 failed under today's rule, against 0, 3, 1, 1 and 1.
- **The wrong-answer part cleared with nothing to spare.** One wrong answer only today's rule failed, and 1 was the limit. It failed that product on the form of its answer, `ANSWER: unknown` not being a number, and called its substance accurate. So it did not see the error either. `both` caught 2 that today's rule passed, each by naming the line.
- **What got through was a missing answer, not a false one.** In the runs, 7 of 450 trials finished with a wrong answer, and none gave a wrong figure. Two named the right company with a hedge on the answer line. Five, on 3 questions of seed 102, said a figure was not in a file that holds it.
- **The test files helped cause those five.** Their sentences are shuffled, so "The churn rate for Q3 settled at 6.4%." follows a sentence about FY2025, and one figure follows "Quillon Biologics is a separate company". The file's heading makes the answer key right, but a careful reader can carry the other sentence over. `both` caught some of these and passed others.
- **Genet and the told crew are level overall.** Question by question, only Genet was right on 11 and only the crew on 9. At 10 companies Genet leads 9 to 2, and at 20 the crew leads 7 to 2. Those splits were looked at after the run, and neither is settled (p about 0.07 and 0.18).
- **Genet stopped on size at 20 companies 7 times in 30, the crew 2.** Each stop came on the lead's own call, after a part the gates refused (3), a part a sub-agent failed or handed back (2), or with no sub-agent at all (2). Its brief came to about 7,000 to 12,000 tokens, which with room for the reply is over the 8,000 cap. On the 4 read closely, the lead had just made at least six reads or searches, and the run stopped there rather than trim what they returned.
- **The built products agree.** `both` failed 0 of 12 right ones, and today's rule 1 of 12. Errors in a file shown were caught 12 of 12 under each, and errors in a file not shown 0 of 12 under each. A pass still checks only the files opened.
- **What this does not show.** These are the same kind of files with new figures, so this cannot show whether the heading sentence misleads where a heading does not apply to a file's lines. It is one review of each product under each rule, on one model. All 39 wrong answers are products after a split. No run went without the rule on these seeds, so the comparison is of reviews, not of whole runs. On this result the rule became the default in v0.10.0, and older tapes replay with `--verify-rule none`.

All 590 reviews, and 449 of the 450 trials, replay with the same results. The other, the told crew on `aggregate-1` of seed 103, stops on size each time, after 6 or 8 calls against the 7 recorded. The likely cause is timing, since its sub-agents run in parallel. Its result does not change.

## 4 November 2026: files a heading does not cover, and what the verifier said

`bash scripts/team_runs.sh refine`, on Haiku 5.5 at effort `low`. Two benches on what the run of 3 November left open. It cost $0.14, against an estimate of $0.17 and a cap of $0.30, and neither bench reached its cap. Each bar was written at the top of the script before the run.

### Does the heading sentence mislead where a heading does not hold?

`verify-bench --arms heading`, on seed 111 with 20 companies: 36 built products, each reviewed under the source rule alone and under the default rule, 72 reviews, $0.08. Each wrong product takes a figure from a line its file's heading does not cover. The company's own file was open in every review.

| The bar | Needed | Result |
|---|---|---|
| The source rule alone catches enough to tell | at least 9 of 18 | 17 |
| Wrong products only the source rule alone fails | at most 1 | **0** |
| Right products only the default rule fails | at most 1 | **0** |
| Controls the default rule catches | at least 5 of 6 | **6** |

| Product | Source rule alone | Default rule |
|---|---|---|
| A sub-heading says FY2025, caught | 6 of 6 | 6 of 6 |
| A paragraph says last year, caught | 6 of 6 | 6 of 6 |
| The file is headed FY2025, caught | 5 of 6 | 6 of 6 |
| The line says FY2025 (the control), caught | 6 of 6 | 6 of 6 |
| Right, failed | 0 of 12 | 0 of 12 |

- **The sentence held.** It lost no catch, and failed no right product. The one difference runs the other way: a sum in a file headed FY2025, which the source rule alone passed.
- **The catches name the line.** One reads "the 49.5 figure is from the '## FY2025 comparatives' section". Under the default rule 23 of 24 named the planted error, and the other failed its product over a different company's line.
- **What this does not show.** The verifier read built products, on one seed, once each. Right products passed under both rules here, so this bench cannot show what the sentence is for, which the run of 3 November showed on real merges. It says nothing of how a lead or sub-agent reads the sentence.

### Told why the verifier failed its product, does a lead put it right?

`rework-bench`: all 30 reworks on the tapes of 3 November, each asked again with and without what the verifier said, 60 trials, $0.06. Before this, the brief said only "Misses: claim is not PASS". Only the lead's call and its tool rounds go to the model. Of the products, 22 were wrong before the rework and 8 right.

| The bar | Needed | Result |
|---|---|---|
| Products wrong before, enough to tell | at least 10 | 22 |
| Wrong products brought right, the reason against the plain brief | at least twice, and 3 more | **11 against 3** |
| Those only the reason brings right, against only the plain brief | at least 3 times | **8 against 0** |
| Right products only the reason turns wrong | at most 1, or 5% | **0 of 8** |

| Brief | Wrong before, right after | Right before, still right | Tokens a rework |
|---|---|---|---|
| Plain, on the tapes | 7 of 22 | 7 of 8 | |
| Plain, asked again | 3 of 22 | 8 of 8 | 4,352 |
| **With the reason** | **11 of 22** | **8 of 8** | 4,459 |

- **The reason cleared its bar.** Product by product it put 8 right that the plain brief did not, and the plain brief none that it did not (sign test, p about 0.008). It talked no right product wrong, though 8 is few.
- **The same brief got 7 on the tape and 3 here, so the gain is likely smaller than 11 against 3.** All 30 first calls of the plain arm are the requests on the tape, byte for byte, with the same system prompt, effort and token limit. The difference is the model's answers varying. Together the two give 5 of 22. Against the tape alone, 11 to 7 would miss the "twice" part of the bar, though all 7 right on the tape are right with the reason too.
- **What stays wrong is mostly a figure left out.** Of the 11 still wrong, 10 decline or leave out one company, such as "not determinable (nine-company sum 531.9 excludes Halvorsen Freight)". One gives a wrong figure. Being told why did not get those leads to take the figure.
- **What this does not show.** No verifier saw these answers, so this is not how many would pass. Each arm asked once, on one model.

### Built, with no paid test yet

- **A round of reads fits the call that carries it.** A round's requests run one at a time, and the round stops when what it returned would not fit the next call, telling the lead how many did not run. Replayed on the tapes of 3 November, all 9 size stops of the told crew and Genet now send a further call that fits, about 5,400 to 6,200 tokens, and the single agent's 90 size stops all go on as well. The other 351 trials replay the same. A tape cannot say whether those further calls reach right answers.
- **`--author-rule headed`** tells the lead and sub-agents the heading sentence, for the leads above who will not take a figure. The verifier's result above allows it, but cannot show it helps an author, so it is off until a whole run measures it.

All 72 reviews and all 60 reworks replay with the same results.

### The whole run, stopped after one seed

`bash scripts/team_runs.sh whole` had its bars written first, and was stopped on purpose just after the first of its five seeds because of what it found. It cost $0.42, including 16 trials of the next seed, which do not count and are run again below.

| Seed 106 | Single | Told crew | Genet |
|---|---|---|---|
| Right, 10 companies, of 24 | | 23 | 24 |
| Right, 20 companies, of 6 | 1 | 4 | 4 |

- **Rounds that fit moved the failure instead of fixing it.** At 20 companies all 14 of the lead's replies cut off at their limit came right after a cut round. Each had between 706 and 2,403 tokens left, and thinking often took all of them, so the reply came back broken, or in 7 cases with no visible text at all. The retry had less room still. So the run ended on a malformed reply where it used to end on size. The replay before this run could show only that the call fit. It said a live run was needed to show what the call would do, and it was.
- **A cut note costs room of its own.** With under 2,500 tokens left, 14 of 15 lead replies ran out right after a cut round, against 1 of 9 on the 3 November tapes, where no cut note was sent. With 3,000 or more, none of 729 ran out, and the largest took 2,416.
- **The fix.** A cut round now gives back reads until a lead has 3,000 tokens to reply in. A round that is not cut is untouched. Replayed with that on, seed 106 at 10 companies is the same in all 48 trials, and the 3 November tapes change only the 99 trials that stopped on size. Of those, 3 still have less room, all single-agent runs whose earlier rounds had already filled the call. The setting is on the tape, so older tapes replay as they ran.
- **Not fixed: a sub-agent's reply can be cut off too.** The gates size a part with 1,500 tokens of room, and a part of 5 files leaves about 2,000. On this seed 7 of 92 sub-agent calls ran out, against 8 of 466 on the 3 November tapes at 20 companies. 43 of 92 replies now mention a heading, against 2 of 466, so the sentence may be lengthening them, though one seed cannot say.
- **A sleeping Mac stops trials.** The machine slept from about 17:26 to 17:41, and a trial's 600-second limit runs on through sleep. Two trials at 20 companies stopped on it, one after a single call. They are the only 2 of the seed's 66 trials that do not replay as recorded, which is how they show.

## 5 November 2026: the rerun, and a verifier that passed a gap

`bash scripts/team_runs.sh rerun`, on Haiku 5.5 at effort `low`, with the fix for cut rounds above. Seeds 107 to 110 at 10 and 20 companies and seed 112 at 20, the told crew and Genet at both sizes and single at 20, with the verifier's reason in the rework brief, rounds that fit and `--author-rule headed` all on. Seed 106 at 10 companies counts as it ran. The bars were written at the top of the script before it ran. It cost $2.08, against an estimate of $1.82, and no run reached its cap. Of that, $0.15 went on 12 trials of seed 108 at 20 companies that a restart of the Mac cut off at 21:19. The script ran that set again from the start the next morning and kept the cut tape under its own name. Those 12 trials do not count, and are reported below.

| The bar | Needed | Result |
|---|---|---|
| Told crew and Genet finish with a wrong figure or name | at most 2 of 300 | **6** (the reference had 0) |
| Tokens a task, told crew | at most 32,525 | 30,105 |
| Tokens a task, Genet | at most 29,395 | 27,840 |
| Single at 20 companies finishes with a wrong figure or name | at most 3 of 30 | 2 |
| Size stops and malformed replies at 20 companies | at most 2 of 60 | **1** (the reference had 9) |
| Genet right at 20 companies | at least 24 of 30 | **21** |
| Answers that decline, leave out or hedge | at most 9 of 300 | **11** (the reference had 19) |
| Right answers | at least 277 of 300 | **276** (the reference had 270) |

| Right | Single | Told crew | Genet |
|---|---|---|---|
| 10 companies, of 120 | | 112 (reference 107) | 116 (reference 114) |
| 20 companies, of 30 | 2 (reference 0) | 27 (reference 27) | 21 (reference 22) |

- **The harm bar failed, so the changes are tested apart before any move to Sonnet.** Six answers finished wrong, against none in the reference.
- **All six begin the same way.** A sub-agent or lead sets a company's true figure aside because of the sentence next to it: a prior-year figure, or the look-alike company's note, in the same paragraph. That happened in the reference too, and there it ended in a declined answer. Here the product answers anyway. It says a company "contributes 0", is "excluded" or is "unresolved", and the verifier passes it, in 5 of the 6 at its first review. Its reasons echo the sample rule, which says a figure no file covers is no fault: "the unopened companies cannot be checked, so the sum is not disproved".
- **Two of the six have a second cause.** On seed 108 the told crew's lead first said a comparison "cannot be settled"; the verifier failed that, and the rework picked a company. On seed 112 a lead read an "FY2025 churn" sentence as a heading and set aside the right company's line under the heading sentence.
- **Across the tapes, the verifier now passes such answers more often.** At 10 companies, lead products that admit a company is missing or set aside, yet give an answer, passed review 3 times of 23 on the reference's tapes and 11 of 22 here. That count is a text search over different products, so it points at the verifier's rule but does not prove it. The test below reviews the same products again.
- **The cut-off trials had a seventh.** Among the 12 trials the restart cut off, the told crew's lead summed 19 of 20 companies, "excluding Kestrel Mill Supply, which it says has no Q2 figure", and the verifier passed it. It does not count, by the rule written before the run, but it is the same failure.
- **Rounds that fit fixed the size stops.** At 20 companies 1 trial of 60 stopped on size or a malformed reply, against 9 in the reference, and the lead's replies cut off at their limit fell from 14 of 50 calls on seed 106 to 4 of 469. The bar also asked for Genet right on 24 of 30 at 20 companies, and it got 21, three of them the wrong answers above, so by the bar as written the size problem stays open.
- **The heading sentence stays off.** Answers that decline or leave out a figure fell from 19 to 11, short of the 9 the bar asked for, and one of the six wrong answers misread it.
- **Single at 20 companies now finishes.** Its size stops go on: 2 right of 30, 2 finished wrong, and most of the rest stopped by the verifier.
- **Reported with no bar: reworks.** After a FAIL, a rework put a wrong product right 9 times of 44, against 7 of 22 on the reference's tapes without the reason. At 10 companies it also turned 3 right products wrong, against 1. These are other products than the rework bench's, most of them partial answers at 20 companies, but the bench's gain did not show in the whole run.
- **Reported with no bar: sub-agents' replies cut off.** At 20 companies 14 of 485 sub-agent calls ran out, against 8 of 466 in the reference. Once, on the cut-off trials, that ended in a size stop.

All 282 trials that finished replay with the same results. The 12 cut off are on their own tape, with no results to match.

### Told to fail a product that leaves out what the goal names

`bash scripts/team_runs.sh gaprule`, on 6 November. Every review after a split on the rerun's tapes, 224 products, asked again under `both` and under `named`, which adds one sentence after the sample rule: "A product that leaves out, sets aside or counts as zero anything the goal names, whatever reason it gives, has not answered the goal: FAIL it and name what is missing." Of the products 187 were right and 37 wrong. 448 reviews cost $0.44, against an estimate of $0.42 and a cap of $0.50. The bars were written at the top of the script before the run, and both had to hold for the sentence to become the default.

| The bar | Needed | Result |
|---|---|---|
| `both` passes enough wrong products to tell | at least 4 | 6 |
| Wrong products `named` passes | at most 1, and fewer than `both` | **0** |
| Right products `named` fails, against `both` | at most 5 more | **25 against 3** |

| Rule | Right answers failed | Passed when recorded, failed now | Wrong answers caught | Wrong answers passed | Tokens a review |
|---|---|---|---|---|---|
| Both | 3 of 187 | 2 of 182 | 31 of 37 | 6 | 4,547 |
| Named | 25 of 187 | 22 of 182 | 37 of 37 | 0 | 4,673 |

One right answer has no verdict under `both`: its reply did not parse.

- **The sentence stops the harm, but fails too many right answers, so it stays off.** Asked again, `both` passed 5 of the 6 products the wrong answers finished on, the five that set a company aside, and `named` failed all 6. But it failed 22 right products that `both` passed, where the bar allowed 5. `--verify-rule named` turns it on.
- **What it fails is a list that is not complete.** Of those 22, about 15 give figures for only some of the companies, such as the top three, and still name the right company or total. The verifier read "leaves out" as not listing every company. 5 did set a company aside and came to the right answer anyway, a fair failure. 2 failed for other reasons.
- **A failure has a cost.** A failed product goes back to the lead, and on the rerun a rework turned a right product wrong 3 times at 10 companies.
- **What this does not show.** It is one review of each product under each rule, on one model, and these are the products the sentence was written from. They were not reviewed under the source rule alone, so this cannot say whether the v0.10.0 rule let them through. A narrower sentence, failing only a product that says it set a named company aside, would keep these catches and fail fewer lists. It is untested, and would need new questions.

All 448 reviews replay with the same results.

## 7 November 2026: a narrower sentence, and a check in code

Both tests go after the harm above: products that set a named company aside, answer anyway, and pass review. Neither is turned on.

### A narrower sentence

`bash scripts/team_runs.sh aside`. The named sentence narrowed to what a product says of itself: "A product that says something the goal names has no figure, could not be found, counts as zero or was set aside has not answered the goal: FAIL it and name what is missing. Keeping out look-alike names or other periods' figures is not this, and a product need not list every figure it used." Two steps for one go-ahead. The first reviewed the gap test's 224 products, which the sentence was written from, so it could not decide anything: it only guarded the second step's spend. The second would have reviewed 318 products no sentence was written from. The first step cost $0.21, against an estimate of $0.22 and a cap of $0.30.

| Rule, on the gap test's 224 products | Wrong passed, of 37 | Right failed, of 187 |
|---|---|---|
| Both | 6 | 3 |
| Named | 0 | 25 |
| Aside | **2** (limit 1) | **17** (limit 8) |

- **It missed even where it was written from, so the second step did not run.** It fell between the two rules it was meant to improve on.
- **It failed 14 right products that list some companies' figures**, the case its last sentence excludes, and 3 more over their subtotals.
- **It passed two wrong products that say just what it describes.** One says Cobalt Ridge "has no FY2026 Q1 figure of its own"; one says Ambergate's figure "is excluded". On Haiku 5.5 the verifier does not reliably tell a list that names some companies from a product that says one has no figure.

### A check in code

The same test as a check the kernel makes, not words for the model: `--gap-check`, off by default. A product the verifier passed whose own words say it has no figure for something, adds 0 for it or set it aside goes back once, with the kernel's reason ("The product says: ... Find that figure in the workspace's files and answer with it"). A product sent back for that which still says so stops the run. The pattern was fixed from the gap test's products and not changed after. On the 318 products no rule was written from, it matched 3 of the 5 wrong products the default rule passes, and 8 right ones.

Before any spend, every rerun and held-out tape was replayed on today's code with and without the check (`data/exp/gapcheck_dry.py`). Of about 1,000 trials, exactly 19 change: the check sends back 10 products that finished wrong and 9 that finished right. That dry run also showed that checking again after the verifier's own reworks stopped 5 right answers and no wrong one, so the second look applies only after a rework the check asked for.

`bash scripts/team_runs.sh gapcheck` then ran those 19 three times. Each trial replays from its tape, and from the request that carries the kernel's reason onward it goes to Haiku and is recorded (`compare --then-live`). Any other way off the tape fails as a replay miss and spends nothing. 33 steps cost $0.13, against an estimate of $0.15 and caps of $1.00. Every other trial matched the dry run.

| Round | Wrong, still wrong | Wrong, put right | Wrong, stopped | Right, still right | Right, stopped |
|---|---|---|---|---|---|
| 1 | 1 | 0 | 9 | 6 | 3 |
| 2 | 4 | 0 | 6 | 3 | 6 |
| 3 | 3 | 0 | 7 | 4 | 5 |

| The bar, on the mean of three rounds | Needed | Result |
|---|---|---|
| Of 10 that finished wrong, still finish wrong | at most 3 | **2.67** |
| Of 9 that finished right, no longer finish right | at most 2 | **4.67** |

- **The check stays off: it stops wrong answers, and as many right ones.** It turned about 7 of 10 wrong finishes into stops, and about 5 of 9 right finishes into stops too, where the bar allowed 2. One right stop in round 3 was on its budget; the rest were the verifier, after a rework that added "provisional" or kept the sentence.
- **No rework put a wrong answer right, in 30 tries.** The leads were told the sentence and asked to find the figure, and in 31 of 51 reworks they asked to read files. They read, and still could not settle which figure was the company's. So what is left of the harm is reading: a true figure next to a prior-year sentence or a look-alike's note. A check after the fact can stop such an answer, but cannot make it right.
- **What this does not show.** These are 19 trials of about 1,000, 11 of them on the tapes the pattern was written from. Whether a stronger model reads these files right is untested.

The live part of each trial is on its own tape, `gapcheck-r<round>-<tape>`. Replaying it needs the original tape as well, and the replay command does not yet take two.

### Sonnet 5.5 on seed 108

`bash scripts/team_runs.sh sonnet`: the first run on Sonnet since 27 October, to ask whether the harm left is Haiku's reading. Seed 108 has the most of Haiku's finished-wrong answers, and the run used the rerun's settings, so each trial pairs with Haiku's on the same question and strategy. A calibration of 4 trials at 20 companies came first, since the kernel's sizes and reply room were measured on Haiku: all 4 right, no stop on size, a malformed reply or the API, the longest 48 of its 600 seconds, $0.53. The 66 trials then cost $5.82, against an estimate of $4.74 and caps of $12.00. Haiku's same 66 cost $0.47.

| Size | Strategy | Trials | Sonnet right | Sonnet wrong | Sonnet stops | Haiku right | Haiku wrong | Haiku stops | Tokens a trial, Sonnet / Haiku |
|---|---|---|---|---|---|---|---|---|---|
| 10 | Told crew | 24 | 24 | 0 | 0 | 22 | 1 | 1 | 21,342 / 25,125 |
| 10 | Genet | 24 | 24 | 0 | 0 | 23 | 0 | 1 | 19,824 / 21,620 |
| 20 | Single | 6 | 0 | 0 | 6 | 0 | 1 | 5 | 54,253 / 55,643 |
| 20 | Told crew | 6 | 6 | 0 | 0 | 5 | 0 | 1 | 41,114 / 62,998 |
| 20 | Genet | 6 | 5 | 0 | 1 | 2 | 2 | 2 | 46,277 / 68,249 |

| The bar, written before the run | Needed | Result |
|---|---|---|
| Sonnet finishes wrong, of 66 | at most 1 | **0** (Haiku 4) |
| Right on the 4 trials Haiku finished wrong | at least 3 | **2** |

- **One bar held and one missed by a trial, so by the rule written first the harm is not only the model's and stays open.** Sonnet finished no answer wrong, against Haiku's 4, and was right on 59 of 66 against 52.
- **Its two misses on Haiku's wrong trials were stops, not wrong answers.** Genet's aggregate-2 merged the right total, 886.1, and the verifier, now Sonnet, failed it: it read Kestrel Mill Supply's April to June figure as the look-alike Kestrel Mills', the trap Haiku's authors fell into, then failed the rework on another point. Single's breadth-2 said its answer was incomplete, with 9 of 20 files unread.
- **Single cannot do 20 companies at this cap on Sonnet either.** All 6 stopped, each having said what it had not read. The told crew got 6 of 6 and Genet 5 of 6, against 5 and 2 on Haiku.
- **Sonnet used fewer tokens a trial than Haiku**, most at 20 companies, and cost about twelve times as much.
- **What this does not show.** One seed, so only a large difference shows. The verifier and the authors were the same model, so this cannot say which one's reading made the difference.

All three tapes are `sonnet-calib`, `sonnet-s108-10` and `sonnet-s108-20`.

### Sonnet 5.5 on seed 110

`bash scripts/team_runs.sh sonnettwo`: the same on a second seed, with no calibration, at $5.80 against an estimate of $5.40 and caps of $12.00. Seed 108's missed bar stands whatever this shows. The bars here: Sonnet finishes wrong at most once in 66, and is right on both trials Haiku finished wrong; if both hold, the next test is a mixed team.

| Size | Strategy | Trials | Sonnet right / wrong / stops | Haiku right / wrong / stops |
|---|---|---|---|---|
| 10 | Told crew | 24 | 24 / 0 / 0 | 23 / 1 / 0 |
| 10 | Genet | 24 | 23 / 0 / 1 | 23 / 1 / 0 |
| 20 | Single | 6 | 0 / 0 / 6 | 1 / 0 / 5 |
| 20 | Told crew | 6 | 5 / 0 / 1 | 5 / 0 / 1 |
| 20 | Genet | 6 | 5 / 0 / 1 | 5 / 0 / 1 |

- **Both bars held.** Sonnet finished nothing wrong (Haiku 2), and named Cobalt Ridge on both breadth-6 trials where Haiku named Halvorsen Freight.
- **But it was not right more often.** 57 of 66 on each model. Sonnet's verifier stopped three right answers that Haiku's passed (991.8, 1082.2, and Cobalt Ridge on breadth-5), so on this seed Sonnet traded two wrong answers for stops.
- **Across both seeds:** Sonnet finished wrong 0 times in 132, against Haiku's 6, and was right on 116 against 109. Its verifier failed 4 right answers, Haiku's on the same trials 0 of those. Sonnet cost $11.62 for the 132; Haiku $0.90.
- **So the next question is which role needs Sonnet.** The authors' reading, the verifier's, or both: a mixed team can tell, and may get most of the gain at a fraction of the cost.

### Haiku authors with Sonnet checking

`bash scripts/team_runs.sh mixed`, on 8 November: Haiku 5.5 as the lead and sub-agents, Sonnet 5.5 as the verifier (`TASKORG_MODEL_NAME_VERIFY`), on seeds 108 and 110 with the rerun's settings, the told crew and Genet. Each call records the model that answered and is priced at that model's rate (`compare --price`). 120 trials cost $2.39, against an estimate of $2.20 and caps of $3.80. The other way round, Sonnet reading and Haiku checking, would have cost about $8.14 by the tapes, close to Sonnet alone, so it was not run.

| 120 trials | Right | Finished wrong | Stopped | Cost |
|---|---|---|---|---|
| Haiku alone | 108 | 5 | 7 | $0.74 |
| Haiku authors, Sonnet checking | 102 | 2 | 16 | $2.39 |
| Sonnet alone | 116 | 0 | 4 | $9.53 |

| The bar, written before the run | Needed | Result |
|---|---|---|
| Finished wrong | at most 1 | **2**, misses |
| Right | at least 105 | **102**, misses |

- **By the rule written first, the reading needs Sonnet.** A stronger checker over Haiku's authors cut wrong answers from 5 to 2, but it did not get Sonnet's result, and it cost right answers.
- **It stopped what it could not trust, right or wrong.** Of Haiku's 5 wrong answers on these trials, 3 came out right and 1 stopped; one stayed wrong, and one new wrong answer appeared. But stops more than doubled, to 16. Some were fair: products that said "partial" or "pending" after a rework. Some were right totals the Sonnet verifier failed (1082.2, 1027.3, 1047.0), as it had on Sonnet's own runs.
- **The authors are the ones to strengthen.** The errors start where a true figure sits next to a prior-year line or a look-alike's note, and the author sets it aside. A checker can only send that back, and Haiku's reworks did not fix it, here or in the gap check.

### Opus 5.5 on seed 108

`bash scripts/team_runs.sh opus`, on 8 November: three models on the same 66 trials, with the rerun's settings. A calibration of 4 trials came first: all right, no stop on size, a malformed reply or the API, the longest 59 of its 600 seconds, $1.17. The 66 trials then cost $11.78, against an estimate of $10.49 and caps of $16.00.

| Seed 108 | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|
| 10 companies, told crew, of 24 | 22 right, 1 wrong | 24 right | 23 right, 1 wrong |
| 10 companies, Genet, of 24 | 23 right | 24 right | 24 right |
| 20 companies, one agent, of 6 | 0, 1 wrong | 0 | 0 |
| 20 companies, told crew, of 6 | 5 | 6 | 6 |
| 20 companies, Genet, of 6 | 2, 2 wrong | 5 | 6 |
| All, of 66 | 52 right, 4 wrong | 59 right, 0 wrong | 59 right, 1 wrong |
| Cost, and a right answer | $0.46, $0.009 | $5.82, $0.099 | $11.78, $0.200 |

| The bar, written before the run | Needed | Result |
|---|---|---|
| Opus finishes wrong | at most 1 of 66 | **1**, holds |
| Splitting at 20 companies | crew and Genet right on at least 9 of 12, one agent on at most 1 of 6 | **12 and 0**, holds |

- **Both bars held.** Opus was right on as many as Sonnet, at twice the price. Its one wrong answer was a sum off by 0.1 (469.9 for 469.8), not a figure set aside; on Genet's aggregate-2 at 20 companies, where Haiku took a look-alike's figure and Sonnet's verifier failed the right total, Opus answered 886.1 and passed.
- **The design holds across three models.** On all three, one agent cannot do the 20-company work at this limit, and the told crew and Genet can: 7, 11 and 12 of 12. The wrong answers that remain are the smallest model's.
- **Genet at 20 companies tracked the model: 2, 5 and 6 of 6.** The lead's plan was the weak part on Haiku; with a stronger reader it matched the crew.

## 7 and 8 November 2026: how many agents a task needs

`bash scripts/team_runs.sh agents`, on Haiku 5.5. Genet began as a question about teams of hundreds of agents: does each one do new work? This sweep asks it directly. The kernel split the files a question names into 2, 4, 10 or 20 parts (`split-N`: one sub-agent a part, no planning call, no gates, the lead merges), against one agent, the told crew and Genet. Questions over all 20 companies, 6 on each of seeds 113 and 114, which no tape had used. Twice: at a call limit of 8,000 tokens, where the 20 files (about 17,500 tokens) do not fit one call, and at 64,000, where they do. Every strategy got 80 calls. 168 trials cost $2.09, against an estimate of $2.20 and caps of $6.00; no part failed on a rate limit. Genet's cap of 4 sub-agents became a setting for this (`Engine(max_workers=...)`, 4 by default); every run before replays the same.

| Call limit 8,000 | Right of 12 | Wrong | Stops | Tokens a question | Calls |
|---|---|---|---|---|---|
| One agent | 1 | 1 | 10 | 54,122 | 10.5 |
| 2 parts | 0 | 0 | 12 | 42,199 | 7.8 |
| 4 parts | 10 | 0 | 2 | 51,630 | 11.8 |
| 10 parts | 11 | 0 | 1 | 64,612 | 22.2 |
| 20 parts | 9 | 1 | 2 | 97,744 | 42.2 |
| Told crew | 11 | 0 | 1 | 50,459 | 12.2 |
| Genet | 9 | 0 | 3 | 54,087 | 12.6 |

| Call limit 64,000 | Right of 12 | Wrong | Stops | Tokens a question | Calls |
|---|---|---|---|---|---|
| One agent | 11 | 0 | 1 | 81,708 | 7.5 |
| 2 parts | 12 | 0 | 0 | 53,102 | 8.2 |
| 4 parts | 12 | 0 | 0 | 40,877 | 10 |
| 10 parts | 12 | 0 | 0 | 63,647 | 22 |
| 20 parts | 9 | 2 | 1 | 100,293 | 42.5 |
| Told crew | 11 | 0 | 1 | 68,844 | 12.2 |
| Genet (one agent every time) | 11 | 1 | 0 | 90,038 | 8.2 |

| The bar, written before the run | Needed | Result |
|---|---|---|
| 8,000: splitting is needed | best split at least 6 more right than one agent | **11 against 1**, holds |
| 8,000: past a handful, more agents do not pay | 20 parts no more right than the better of 4 and 10, at 1.3 times its tokens or more | **9 against 11, 1.51 times**, holds |
| 8,000: Genet's own plan | within 1 of the best split, at most 1.2 times its tokens | **9 against 11**, 0.84 times, misses |
| 64,000: one is enough | no split more than 1 right more than one agent | **12 against 11**, holds |
| 64,000: Genet stays one agent | at least 10 of 12 | **12**, holds |

- **About four was the right number.** At both limits 4 parts cost the fewest tokens of the settings that worked, and were as right as any. Ten parts were as right for 1.25 to 1.55 times the tokens.
- **Twenty agents did worse and cost about twice as much.** They were right on 9 of 12 at both limits, and made 3 of the sweep's 5 wrong finishes: totals from 20 reports that left a company out or took a look-alike's figure (952.8, 932.3), and one right name the grader could not read for the figure after it. Each part saw one file, so none could set a company against its look-alike, and the merge had 20 reports to add.
- **Too few fails when a part does not fit.** At 8,000, 2 parts of 10 files stopped on size 10 times of 12. At 64,000 they were fine.
- **Where the work fits, splitting was still cheaper.** At 64,000 one agent spent 81,708 tokens a question, and 4 parts 40,877, at least as right. One agent sends everything it has read again with every round; a part carries only its share. Genet's rule splits only work that does not fit one call, so it stayed one agent every time, at 2.2 times what 4 parts spent. The simulator showed the same on 27 October; this is the first live measure. Genet does not use prompt caching, under which a re-sent prefix costs about a tenth, and that may close much of this gap: test it before the rule changes.
- **Genet's own plan missed its bar by one question.** Its leads staffed 4 parts in 11 of 12, as the told crew's did. It lost one to a size stop, one to a refused part and one to a look-alike it left unresolved; the crew lost one. Twelve questions cannot tell that from noise, but by the bar the lead's plan is the weak part, not the count.
- **What this does not show.** It is a small model of large work: 20 files of about 900 tokens. One model. Twelve questions a cell, so differences of one or two are noise.

The tapes are `agents-s113-8000`, `-s113-64000`, `-s114-8000` and `-s114-64000`.

### Prompt caching on the questions that fit

`bash scripts/team_runs.sh cache`, on 8 November. With `TASKORG_MODEL_CACHE=1`, a call that may go on to tool rounds is sent in blocks cut where each round begins, the newest round marked, so the next round reads what came before from the cache at a tenth of the input price; a write costs a quarter more. The model reads the same text. The sweep's 64,000 questions again, one agent, 4 parts and Genet, 36 trials, $0.31 against an estimate of $0.25 and caps of $1.00.

| Strategy | Right, uncached / cached | Cost a question, uncached / cached | Calls a trial, uncached / cached |
|---|---|---|---|
| One agent | 11 / 9 | $0.0129 / $0.0090 | 7.5 / 5.8 |
| 4 parts | 12 / 11 | $0.0079 / $0.0080 | 10.0 / 10.0 |
| Genet (one agent every time) | 11 / 11 | $0.0140 / $0.0089 | 8.2 / 6.6 |

| The bar, written before the run | Needed | Result |
|---|---|---|
| Answers hold | each within 1 of uncached | **one agent 9 against 11**, misses |
| Caching pays | one agent's cost a question down 30% or more | **29.8%**, misses |
| The gap | cached one agent at most 1.25 times cached 4 parts | **1.12**, holds |

- **Caching stays off: both bars it needed missed.** One by a hair, one by an answer.
- **Most of the sweep's cost gap was the missing cache.** Cached, one agent cost 1.12 times what 4 parts did, against 1.63 times uncached in this run's terms. So, with caching, the should-we rule would need no cost term. 4 parts gained nothing from it: a part reads in one or two rounds, and the write costs more than the reads save.
- **But the cached single agent read less and was wrong more.** It made 5.8 calls a trial against 7.5, and finished 3 answers wrong where uncached it finished none, one of them a look-alike (Halvorsen Freight Labs). Genet, also one agent here, made fewer calls too and kept its 11. Twelve trials cannot tell the block format from chance, so before caching is used, the uncached and cached single agent need running again side by side.

### The sweep on Sonnet 5.5

`bash scripts/team_runs.sh sonnetsweep`, on 8 November: the sweep's 8,000 questions again, seeds 113 and 114, on Sonnet 5.5, to see whether "about four" holds on a stronger reader. One agent, 4, 10 and 20 parts and Genet, 80 calls each, Haiku's bars. 60 trials cost $10.76, against an estimate of $9.40 and caps of $12.00.

| Call limit 8,000, of 12 | Right, Sonnet | Right answer, Sonnet | Tokens a question, Sonnet | Right, Haiku | Tokens a question, Haiku |
|---|---|---|---|---|---|
| One agent | 0 | 0 | 54,203 | 1 | 54,122 |
| 4 parts | 11 | 12 | 38,770 | 10 | 51,630 |
| 10 parts | 12 | 12 | 60,607 | 11 | 64,612 |
| 20 parts | 12 | 12 | 91,285 | 9 | 97,744 |
| Genet | 11 | 12 | 41,347 | 9 | 54,087 |

"Right answer" counts the product's answer whatever the verifier said; "right" also needs it verified.

| The bar, written before the run | Needed | Result |
|---|---|---|
| Splitting is needed | best split at least 6 more right than one agent | **12 against 0**, holds |
| Past a handful, more agents do not pay | 20 parts no more right than the better of 4 and 10, at 1.3 times its tokens or more | **12 against 12, 1.51 times**, holds |
| Genet's own plan | within 1 of the best split, at most 1.2 times its tokens | **11 against 12, 0.68 times**, holds |

- **On Sonnet the count changed the cost, not the answer.** Every split got the right answer on all 12 questions, at 4, 10 and 20 parts alike. Nothing finished wrong in 60 trials. The two that stopped were right totals (1106.0) the Sonnet verifier failed, one under 4 parts and one under Genet, as it did on seeds 108 and 110.
- **About four still holds, now on cost alone.** 4 parts spent 38,770 tokens a question, 10 parts 1.56 times that and 20 parts 2.35 times, for no more right answers. At Sonnet's price that is $0.114, $0.190 and $0.297 a question.
- **Twenty agents' wrong answers on Haiku were the smaller model's.** Haiku's 20-part merges left a company out or took a look-alike's figure; Sonnet's added the same 20 reports right every time. The cost of twenty does not depend on the model; the risk does.
- **Genet's own plan held its bar here, where on Haiku it missed by one.** Its leads staffed 4 parts every time (Haiku's 11 of 12), none refused, at 1.07 times the fixed 4 parts' tokens.
- **One agent failed honestly.** It could not read 20 files at this limit on either model. On Sonnet, 10 of its 12 answers said they were incomplete, provisional or partial, and the verifier stopped all 12, including the two that named a wrong company from the files it had read without saying so. The limit is the one we set, so this says only that splitting works when the work does not fit one call.
- **What this does not show.** The same 12 questions as Haiku's, so the pairing is exact but small. One call limit; the 64,000 half was not rerun.

The tapes are `sonnetsweep-s113-8000` and `sonnetsweep-s114-8000`.

## 9 November 2026: a head-to-head with CrewAI on public documents

`bash scripts/team_runs.sh headtohead`: Genet against CrewAI 1.15.30 on two public benchmarks, with the plan and its bars written first in [HEAD_TO_HEAD.md](HEAD_TO_HEAD.md).
- **Model and limits:** Haiku 5.5 at effort low. Each trial got a call limit of 100,000 tokens, 80 calls, 1,200 seconds and pages of 16,000 characters. Genet's agents get 6 tool rounds.
- **CrewAI's setup:** hierarchical, a manager and 4 readers, on CrewAI's own Anthropic provider with native tool calls. Genet's raw client sits underneath it, so every call was sized, capped, priced and taped the same way.
- **Loong:** 40 questions over 2024 SEC filings, 10 each of spotlight, comparison, clustering and chain. Each question carries 240,000 to 517,000 characters of filings. Sonnet 5.5 judged the answers with Loong's own prompt.
- **HotpotQA:** 20 distractor questions, scored by exact match.
- **Cost:** the calibration cost $0.26. The main run cost $2.59: Loong $1.92, HotpotQA $0.19 and the judge $0.48. The rough estimate before calibration was $10 to $16.

One rule changed after the calibration and before the main run had results. Right on Loong became a judge score of at least 80 in a finished run, where the plan had said 100. Sonnet gave 92 to 97 to calibration answers that matched the gold one, one of them word for word, so no answer reached 100 (see HEAD_TO_HEAD.md).

| Loong, of 40 | One agent | Told crew | Genet | CrewAI |
|---|---|---|---|---|
| Right | 22 | 20 | 20 | **25** |
| Right answer, stopped or not | 25 | 22 | 21 | 25 |
| Finished wrong | 15 | 14 | 12 | 15 |
| Stopped by the checker | 3 | 6 | 8 | none; CrewAI has no checker |
| Loong's average score | 68.7 | 59.8 | 59.4 | 66.7 |
| Score of 100 | 2 | 2 | 1 | 0 |
| Split | 0 | 40 | 13 | 40 |
| Tokens a question | 74,697 | 94,722 | 87,694 | 127,338 |
| Cost a right answer | $0.016 | $0.025 | $0.022 | $0.024 |

| HotpotQA, of 20 | One agent | Told crew | Genet | CrewAI |
|---|---|---|---|---|
| Right, exact match | 12 | 9 | 12 | 8 |
| Split | 0 | 20 | 0 | 20 |
| Tokens a question | 8,329 | 18,625 | 10,010 | 12,798 |

| The bar, written before the run | Needed | Result |
|---|---|---|
| Loong accuracy | Genet at least the best of the others less 3 | **20 against CrewAI's 25**, misses |
| Loong cost | Genet's tokens a question and cost a right answer at most CrewAI's | **87,694 and $0.022 against 127,338 and $0.024**, holds |
| Loong wrong finishes | Genet at most CrewAI's | **12 against 15**, holds |
| HotpotQA, one agent is enough | Genet one agent on at least 18 of 20 | **20 of 20**, holds |
| HotpotQA at its cost | Genet within 1 right of one agent, at most 1.3 times its tokens | **12 against 12, 1.20 times**, holds |

- **CrewAI was right on 5 more Loong questions than Genet.** Its answers, read side by side, account for the gap:
  - 3 were Genet's own misses: a count of 1 where the answer was 2, and two "cannot be determined", one of them after a split.
  - 1 was a right answer stopped by Genet's checker.
  - 1 came, net, from the judge scoring the same content differently: 62 against 80 and 72 against 82 went against Genet, 80 against 72 went for it.
- **The loss is where Genet split.** Its lead proposed on 14 questions; the gates refused one part, and Genet split on 13. On those 13 Genet was right on 4, and its checker stopped 5. One agent and CrewAI were right on 7 each, and the told crew on 4. On the 27 questions Genet kept single, it was right on 16, against one agent's 15. So the gate kept what one agent does. Genet's own team did worse than CrewAI's crew and one agent wherever it ran, whether the lead was told to split (the told crew) or the gates decided (Genet). That team is the lead, the parts, the merge and the checker.
- **One agent came close to CrewAI.** It was right on 22 against 25, at 59% of CrewAI's tokens. With a 100,000-token call and paged reads, most of these questions fit one agent.
- **The checker trades both ways.** It stopped right answers: 3 of one agent's, 2 of the told crew's and 1 of Genet's. Its contenders finished wrong 12 to 15 times, CrewAI 15.
- **The cut-off decides the accuracy bar.** The judge docks points for detail it cannot check, and CrewAI's answers carry more of it. At a score of 95 or more, one agent has 17 right and CrewAI 7.

  | Cut-off | One agent | Told crew | Genet | CrewAI | Bar |
  |---|---|---|---|---|---|
  | 70 | 22 | 20 | 21 | 26 | misses |
  | 80, the rule set before results | 22 | 20 | 20 | 25 | misses |
  | 90 | 21 | 17 | 19 | 19 | would hold |

  The rule was set from the calibration before results, so the bar misses.
- **Chain questions failed for everyone,** 0 to 2 right of 10. Loong's gold answers label years by when a filing was made, so their "2023 to 2024" is fiscal 2022 to 2023. Every contender read the fiscal years correctly.
- **On HotpotQA the gate kept short work single.** Genet stayed one agent on all 20 questions and matched one agent's 12 right at 1.20 times its tokens.
  - CrewAI's 8 by exact match is 12 in substance. Four right answers came wrapped in `<answer>` tags, because its agents took our own instruction, "ANSWER: &lt;answer&gt;", literally.
  - Exact match is strict for everyone: "Rob Sitch" for Robert Ian "Rob" Sitch counts as wrong.
- **Every tape replays exactly:** 256 trials and 176 verdicts, with no request missing from its tape. 20 verdicts read by hand agree with the answers they score.
- **The run took about 5 hours by the clock, against 1.4 hours of trial time.** It paused between trials, probably while the Mac slept. No trial stopped on time or on the API.
- **What this does not show:**
  - One subset of one benchmark, at one call limit, on one model, so a difference of 3 or fewer of 40 is noise.
  - CrewAI as we configured it, not as an expert would.
  - A judge whose wording moves a score by a few points either way.
  - Prompts that ask for "ANSWER: &lt;answer&gt;", which is our wording.

### Why Genet's splits lost: the tapes read again

Every Genet-side Loong trial was replayed from its tape with its whole record kept: the plan, each part's report, every merge, and the checker's verdicts. No calls were made. The script is `data/exp/h2h_splits_read.py`.
- **The lead's choice to stay single was sound.** It was asked to plan on all 40 questions, since no question fits one call. It kept 26 to one agent, saying one agent could search each filing in turn. On those it was right on 16, against one agent's 15.
- **Splits lost on line names.** Loong's questions use generic line names such as 'Total Operating Revenue', 'long-term borrowings' and 'Cash and Cash Equivalents at End of Period'. Its instruction says to ignore content not found in the statements. On 9 questions, a split run's parts reported that the named line is not in their filing, and gave the closest one: "no line labeled 'Total Operating Revenue'; the closest is 'Revenue'". On those 9:

  | Of the 9 questions | Right |
  |---|---|
  | One agent | 6 |
  | CrewAI | 6 |
  | Genet | 3 |
  | Told crew | 3 |

  That is the whole of Genet's deficit against one agent on the questions it split, and 3 of its 5 against CrewAI.
- **How each of Genet's three losses went.** The parts each flagged the missing name. The lead's merge carried the flags up as a hedge: "cannot be determined", "3, or 2 on a strict reading", "undetermined". The checker failed it as not an answer, and the rework went one of three ways:
  - Still hedged, on total operating revenue.
  - Strict and wrong, on the cash count: it counted only exact labels and answered 1 for 2.
  - Right, but failed again as resting on an estimate, on long-term borrowings.

  One agent and CrewAI's manager used the nearest line without comment. A single agent reads every filing itself, so a name that does not match never reaches the lead as three separate caveats.
- **Without such a flag, splits mostly worked.** On the questions that are not chain questions, the told crew was right on 18 of 22 and Genet on 3 of 5.
- **The checker failed products on 11 of Genet's 40 trials** (19 FAILs), 8 of the told crew's (14) and 10 of one agent's (13). It stopped right answers 1, 2 and 3 times.
- **The fix, built on the operator's go-ahead and run on the 9 questions (below).** `--author-rule wording` tells every writer, but not the plan or the checker, that a filing may name a line differently from the goal. Where no line carries the goal's name, they use the line that measures the same thing, say which, and answer.
  - `bash scripts/team_runs.sh wording` reruns the told crew and Genet with that note, a y for each step:
    1. The 9 questions, about $0.35.
    2. All 40, about $1.25.
  - The bars are at the top of that script, written before the run. On the 9, together right on at least 9 of 18, against 6, with at most 4 wrong. On the 40:
    - Genet right on at least 22;
    - each team right on at least 16 of the other 31;
    - Genet wrong at most 15 times.
  - The scorer is `data/exp/wording_read.py`.

### The wording note on the 9 questions

`bash scripts/team_runs.sh wording`, step 1, on 9 November. The told crew and Genet reran the 9 questions with `--author-rule wording`, on the same model, limits and judge. The run cost $0.26: $0.21 for 18 trials and $0.05 for the judge.

| The 9 questions | Right | Finished wrong | Stopped by the checker | Tokens a question |
|---|---|---|---|---|
| Told crew, 9 November | 3 | 3 | 3 | 120,814 |
| Told crew, with the note | 4 | 3 | 2 | 80,645 |
| Genet, 9 November | 3 | 1 | 5 | 143,672 |
| Genet, with the note | 4 | 3 | 2 | 91,126 |
| One agent, 9 November | 6 | 2 | 1 | 89,773 |
| CrewAI, 9 November | 6 | 3 | 0 | 99,287 |

| The bar, written before the run | Needed | Result |
|---|---|---|
| Together right | at least 9 of 18 | **8**, misses |
| Together finished wrong | at most 4 | **6**, misses |

By the rule written first, step 2 did not run, and the note stays off.
- **The writers did what the note asked.** Parts named the line they used and answered with it. Merges gave an answer in place of "cannot be determined". The checker's stops fell from 8 to 4, and the two teams used about a third fewer tokens.
- **Long-term borrowings was fixed for both.** Each team named Broad Street Realty, and the checker passed it.
- **The checker had not been told.** It failed products for using a nearest line, as the note asked: "substitutes closest-match lines". On total operating revenue, Genet's answer was right (88) and stopped. Its rework compared a figure from the wrong quarter, and the checker caught that.
- **"The line that measures the same thing" also reached too far.** On the cash count both teams counted Cross Timbers' "Cash and short-term investments" and answered 3. Loong's answer is 2, which one agent gave. On undistributed profits, a proxy line led Genet to a wrong company, and the checker passed it on rework.
- **Stops became wrong finishes.** Four of the old stops now finish with a wrong answer: total profit for both teams, undistributed profits for Genet, and a grouping by change in cash for the told crew. Two of the told crew's old wrong finishes now stop instead. That is why wrong finishes rose from 4 to 6.
- **Reading.** Telling writers to substitute fixes the hedging. Without a rule for when a nearby line is the same measure, it trades stops for wrong answers. The checker then disagrees with the writers about substitution, in both directions. Both tapes replay exactly: 18 trials and 18 verdicts.

The tapes are `h2h-calib-genet`, `h2h-calib-crewai`, `h2h-calib-judged`, `h2h-loong-genet`, `h2h-loong-crewai`, `h2h-hotpot-genet`, `h2h-hotpot-crewai`, `h2h-loong-judged`, `h2h-wording-nine` and `h2h-wording-nine-judged`. They hold SEC filing text and HotpotQA paragraphs (CC BY-SA 4.0), so they stay local until their licences are checked. The scorer is `data/exp/h2h_read.py`.

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

The Claude runs' results are in `data/compare/` and their tapes in `data/tapes/`, and both are published as releases, [through 29 October](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261029), [for 2 November](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261102), [for 3 November](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261103) and [for 3 to 6 November](https://github.com/jrodriguez4505/Genet/releases/tag/tapes-20261106), each with a `REPLAY.md` that gives each tape's command. The run files in `data/` and `Data2/` stay on the operator's machine and are not committed. `Data2/data/` is a backup copy of `data/`. The four episodes in `data/episodic/` that have no saved run (`mx-001`, `pw-001`, `so-001`, `so-live-gate`) came from the stub adapter, not from a live model.
