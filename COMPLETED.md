# Genet — completed work

Apache-2.0. Public repo: https://github.com/jrodriguez4505/Genet · Website: https://jrodriguez4505.github.io/Genet/

## v0.13.0 — November 2026: when to split, and what the tapes said

**Why.** v0.12.0 left Genet behind CrewAI on real filings, with its losses on the questions it split. Three fixes after the split had each let more wrong answers through. Two things were left to try: the decision to split itself, and reading every small difference so far for what was noise.

**Built.**
- **The split rule** (`--split-policy reads`, now the default; `compare`'s `genet`). With paged reads, when one agent reading a page of each file can hold what the goal names in one call, there is no planning call and the lead works alone. Otherwise the lead plans and the gates judge the plan as before. `genet-measured` is Genet as it was.
- **Two fixes to what the verifier is shown.**
  - The kernel's quote check reads zero-width spaces as space. Loong's 2024 filings carry them after many figures, and 31 of the check's 190 flags on the Loong tapes were false for that alone.
  - The verifier's view marks where the product's text ends. The kernel's evidence list, quote check and sources follow the product, and the verifier had read them as part of it.
- **Exact replays.** A tape marks each exchange with its trial, so one strategy replays as exactly as the whole run. Each setting that changed is named in a run's config, and a tape from before replays under what it ran with.
- **Noise with every comparison** (`taskorg paired`, `taskorg/paired.py`): an exact sign test on the questions where two arms differ, and a bootstrap range on tokens.
- **A fix measured from the first request it changes** (`compare --then-live` with `--fixed-quotes` or `--marked-review`): a trial replays its tape up to that request and runs live from there.
- **Long notes** (`compare --pad-notes`), so the generated questions can be asked past a real call limit. **Loong's remaining questions** (`--which rest`).
- **Two reworks, measured and left off:** one that may read after a merge (`--rework-reads`, 9 November) and one that keeps the pages its failed product read (`--rework-keeps`).
- **New run modes in `scripts/team_runs.sh`:** `rereads`, `splitrule`, `keeppages`, `scale`, `splitagain`, `firstjudge`, `quotefix` and `markedreview`. Those that test a change have their bars written before the run; the last three measure, with their plan written first. `quotefix` and `markedreview` wait while the machine is short of memory.

**What the live runs showed** (10 and 11 November, about $6 in all). See [docs/LIVE_TESTS.md](docs/LIVE_TESTS.md).
- **Every right or wrong difference on Loong so far was within noise,** CrewAI's 25 against Genet's 20 included (p 0.12). Genet's lower tokens against CrewAI were not: 39,600 fewer a question.
- **The split rule held its three bars where it acts.** Over two draws of 54 new Loong questions, on the 51 trials where Genet had split:
  - right rose from 16 to 24 (+8 / -0, p 0.008);
  - finished wrong rose from 24 to 26;
  - it finished 31% sooner, at about the same tokens.
- **At a real call limit one agent kept up.** With the sweep's notes grown past 100,000 tokens, one agent that searched was right on 6 of 12, 4 parts on 4 and Genet on 4, within noise. The sweep's win for splitting at 8,000 was that cap's. What splitting bought beyond noise was time: 34 to 57% sooner on large work.
- **The rework is about even on real filings.** Under the split rule, 24 of 108 trials were reworked and ended 9 right, 11 wrong and 4 stopped. The verifier had failed 7 right products of the 24.
- **The two verifier fixes changed no answers beyond noise.** The quote fix saved three reworks that only false flags had caused. With the view marked, the verifier failed 20 products where it had failed 28, and the false "ANSWER line is not last" fell from 4 to 1.
- **Kept pages cost more and gained nothing,** so they stay off.

**Left open.**
- Whether a wrong answer or no answer is the better end for a rework on real filings.
- Whether the gates should count time: splitting was faster on large work and slower on small.
- A Loong run of today's Genet beside CrewAI. The 9 November comparison is of Genet before the split rule.
- The tapes since 6 November, which wait on a licence check before they are published.

## v0.12.0 — November 2026: how many agents, three models, and an outside comparison

**Why.** Every result so far compared Genet with its own baselines, on one model, with the agent count set by Genet's own gates. Three questions were left: how many agents a task like this needs, whether the findings hold on stronger models, and how Genet does against an established framework on public questions.

**Built.** Everything below is off by default, and v0.11.0's tapes replay as before.
- **Fixed splits for measuring** (`split-2`, `split-4`, `split-10`, `split-20`). The kernel splits a goal's files evenly, and each engine has its own worker cap.
- **Prompt caching** (`TASKORG_MODEL_CACHE`), priced per model. **A model and price per role** (`--price MODEL=IN/OUT`), so a Sonnet verifier can check Haiku writers.
- **Two checks for answers that set a figure aside.** `--verify-rule aside` adds a verifier sentence, and `--gap-check` sends such an answer back for one rework. **`compare --then-live`** replays a tape until a chosen request, then goes live.
- **Public benchmarks in `compare`** (`taskorg/benchmarks.py`):
  - Loong's English SEC-filing questions and HotpotQA, with `--benchmark`, `--questions`, `--docs`, `--which main|calibration|fresh` and `--ids`;
  - paged reads (`read:PATH@N`, `--page-chars`);
  - `h2h-judge`, which runs Loong's own judge prompt on Sonnet. An answer counts as right at a score of 80 or more.
- **A raw client for other frameworks** (`taskorg/rawcall.py`). It sizes, caps, prices and tapes every call. `scripts/h2h_crewai.py` runs CrewAI 1.15.30 on it, with CrewAI's own tool calls and telemetry off.
- **Notes for a line a filing names differently** (`--author-rule wording|same`, `--verify-rule same`).
- **New run modes in `scripts/team_runs.sh`:** `sonnet`, `sonnettwo`, `agents`, `cache`, `mixed`, `opus`, `sonnetsweep`, `headtohead`, `wording` and `samenote`. Each has its bars written before it ran.

**What the live runs showed** (7 to 9 November, about $45 in all). See [docs/LIVE_TESTS.md](docs/LIVE_TESTS.md).
- **About four agents was right.** On Haiku at an 8,000-token call limit, 4 parts were right on 10 of 12 and 20 parts on 9, at about twice the tokens. Where the work fits one call, 4 parts cost half what one agent did. On Sonnet every split got the right answer on all 12, and the count changed only the cost; the checker stopped one of 4 parts' right answers, so 4 parts finished 11 right.
- **Three models on the same 66 trials.** Haiku, Sonnet and Opus were right on 52, 59 and 59, and finished wrong 4, 0 and 1 times. A Sonnet verifier over Haiku writers did not reach Sonnet alone.
- **Prompt caching cut one agent's cost by 30%**, but the cached agent read less and finished wrong more often, so it is off.
- **Against CrewAI on Loong's 40 questions over SEC filings:**
  - CrewAI was right on 25, one agent on 22 and Genet on 20, so Genet missed its accuracy bar.
  - It held the other bars: fewer tokens a question (88k against 127k), lower cost a right answer, and fewer wrong finishes (12 against 15).
  - On HotpotQA Genet stayed one agent on all 20 and matched it.
  - Genet lost where it split. Its parts each reported that the line a question names was missing, and its merge hedged.
- **Neither the wording note nor the narrower same-measure note recovered those answers.** Each turned stops into wrong answers, on the in-sample 9 and on 12 fresh questions.

**Left open.**
- Line names that a filing words differently, after a split.
- The aside and gap checks, which each stopped too many right answers.
- A split rule that weighs cost as well as fit.
- The lead's variance in whether to split: 5 against 8 of 12 on two runs of the same questions.

## v0.11.0 — November 2026: a lead told why, and rounds that fit

**Why.** The run of 3 November left four things to try. Nobody had tested the heading sentence on files where a heading does not hold. The lead's rework brief never said what the verifier objected to, in 0 of 32 requests. A lead's own reads could overflow its next call and stop the run. And most wrong answers were an author refusing a figure that is in the file.

**Built.**
- **The verifier's reason in the rework brief** (`loop.py`), up to 1,200 characters. `--no-rework-reason` leaves it out, as tapes before this version recorded it.
- **Rounds that fit.** A round's tool requests run one at a time, and the round stops when what it returned would not fit the next call, telling the lead how many did not run. A cut round gives back reads until a lead has room to reply (`round_reply_tokens` on the adapter, which a tape records, so older tapes replay as they ran) (`loop.py`).
- **`--author-rule headed`** tells the lead and sub-agents the heading sentence. It is off by default until a whole run measures it.
- **`rework-bench`** (`taskorg/rework_bench.py`). The tapes' reworks asked again, with and without the reason, product by product.
- **The verify bench's `heading` arm.** Wrong figures from a section, a paragraph or a whole file that a heading does not cover, with the company's file always open.
- **`scripts/team_runs.sh refine`.** Both benches, with their bars written before the run.
- **`--verify-rule named`**, off by default: the default rule and one more sentence, that a product that leaves out, sets aside or counts as zero anything the goal names has not answered it (`checks.NAMED_RULE`). `merge-bench` reviews under it too.
- **`scripts/team_runs.sh whole`, `rerun` and `gaprule`.** Whole runs with every change on, and the test of that sentence, each with its bars written before the run.

**What the live runs showed** (4 November, Haiku 5.5, $0.14). The heading sentence held: the default rule caught 24 of 24 wrong products against 23 of 24 for the source rule alone, and failed none of 12 right ones. Told the reason, leads put right 11 of 22 wrong products, against 3 for the same brief without it, and talked none of 8 right ones wrong. The same plain brief got 7 of 22 on the tapes, so the gain is likely smaller than that.

The whole run (4 to 6 November, $2.94 with a first try stopped after one seed and the sentence's test) took the told crew and Genet over five more seeds. The first try found that a cut round left a lead too little room to reply, so a cut round now gives back reads until a lead has 3,000 tokens. The rerun's harm bar failed: 6 of 300 answers finished wrong, against none before. In 5 a product set a company's true figure aside and the verifier passed it. Stops on size or a malformed reply at 20 companies fell from 9 of 60 to 1, but Genet was right on 21 of 30 there, short of its bar's 24. The told crew got 139 of 150 and Genet 137. The `named` sentence failed all 37 wrong products on the rerun's tapes, but 22 more right ones than the default, against a limit of 5, so it stays off. See [docs/LIVE_TESTS.md](docs/LIVE_TESTS.md).

**Left open.** A verifier that passes a product setting part of the goal aside (question 15 in [ARCHITECTURE.md](ARCHITECTURE.md)). Genet's right answers at 20 companies after the size fix, and sub-agent replies cut off at their limit (question 16). `--author-rule headed` cut answers that decline from 19 to 11 of 300, short of its bar's 9, so it stays off (question 17). Of the 11 reworks still wrong on the bench, 10 decline or leave out one company.

## v0.10.0 — November 2026: the verifier told what its sources are

**Why.** On real merges the verifier failed about 1 right answer in 3. Two sentences nearly stopped that on the tapes that suggested one of them, so they waited for new questions.

**Built.**
- **The rule is the default.** After the source rule, the verifier is told its files are a sample, so a figure no file covers is no reason to FAIL, and that a line with no year takes its file's heading (`checks.VERIFY_RULE`, `loop.py`).
- **`--verify-rule`** on `compare` and every run command: `both` (the default), `told`, `headed` or `none`. `none` is the brief before this version, which older tapes replay, and replaying one without it gets a note.
- **`merge-bench`** replaces whatever rule a tape was recorded under, so `none` means none on a tape recorded under another, and reports each rule against the first, product by product. Its first rule was called `today`.
- **`scripts/team_runs.sh heldout`.** Five seeds no tape had used, resumable, with its bar written before the run.

**What the live run showed** (3 November, Haiku 5.5, $2.40). The rule cleared its bar. Of 220 right answers, the source rule alone failed 69 and the rule 6, and 64 to 1 product by product. Of 39 wrong answers it caught 37, against 36. The single agent got 57 of 150, the told crew 134 and Genet 136. Full results are in [docs/LIVE_TESTS.md](docs/LIVE_TESTS.md).

**Left open.** A pass still checks only the files opened. These seeds are the same kind of files with new figures, so nothing yet shows whether the heading sentence misleads where a heading does not apply (question 15 in [ARCHITECTURE.md](ARCHITECTURE.md)). The run found two new problems: a lead's own reads overflowing its next call at 20 companies, and answers of "not found" that finish as complete (questions 16 and 17).

## v0.9.3 — November 2026: files a plan leaves out, and benches for the second plan and the verifier

**Why.** The check of v0.9.2 left two questions a run could not answer. Every lead's first plan fit, so no real lead had written a second. And the verifier failed a right answer on 4 of 5 split runs.

**Built.**
- **Files a plan leaves out.** Files the goal names that no part names go to the lead to cover in the merge, unless the context already gives what they hold (`loop.py`).
- **`merge-bench`** (`taskorg/merge_bench.py`). The verifier's requests from the tapes, reviewed again under each rule, product by product.
- **`scripts/live_session.sh`.** The key is entered once for a sitting and kept in that window's memory, and each run still waits for its own `y`.
- **`plan-bench`** (`taskorg/plan_bench.py`). The run is handed a first plan the gates refuse, in one of three shapes, and only the lead's second planning call goes to the model.
- **The verify bench's `split` arm.** Products shaped like a lead's merge, with group subtotals and no file cited. Of each wrong kind, one has its error in a file the layered pick shows, and one in a file it does not.
- **The setups `independent-told`, `-headed` and `-both`.** The verifier is told its sources are a sample, that a line with no year takes its file's heading, or both. They are off everywhere else, and a plain run of the bench leaves them out, so the 29 October tape still replays.

**What the live run showed** (3 November, Haiku 5.5, $0.10). All 18 second plans were admitted, and 17 covered every file. One left out 5 files, among them the one with the right answer. The clean merges did not reproduce the false failures: under either rule the verifier failed none of 12 right products, caught all 12 errors in a file it was shown, and none of 12 in a file it was not. So those products cannot separate the rules. On the real merges they can: today's rule failed 34 of 104 right answers, and told both sentences the verifier failed 3, with 18 of 19 wrong answers caught and none passed ($0.56). See [docs/LIVE_TESTS.md](docs/LIVE_TESTS.md).

**Left open.** The two sentences are off until new questions confirm them, because one came from reading these same merges (question 15 in [ARCHITECTURE.md](ARCHITECTURE.md)).

## v0.9.2 — November 2026: a sub-agent's own room, and a second plan

**Why.** The check of v0.9.1 stopped three runs at 20 companies. One stopped 44 tokens over the cap, keeping room for the lead's plan reply. Two had plans refused with no way back.

**Fixed.**
- **A sub-agent's room.** It keeps room for its own replies and for what the adapter expects of a sub-agent, 1,500 tokens on Claude, measured on the tapes. The lead's plan reply no longer counts (`loop.py`, `anthropic_live.py`).
- **What the gates charge a part.** A part must fit a sub-agent's own call: its brief, what reading adds to its files, and that same room. The gates and the size check now agree, and a large plan reply no longer refuses a part that fits (`gates.py`, `loop.py`).
- **A second plan.** A plan with a part too big gets one more planning call, told what the gates measured, when a split could still be paid for. There is no third. The first plan stays on the record, and leaves the shared context, where every plan writes itself (`loop.py`, `run.py`).

**What the live run showed** (3 November, Haiku 5.5, $0.06). At 20 companies, no stop on size: all 6 leads split, 5 reached the right answer and 4 were verified. On the code before these fixes the same tape stops one of them on the size check. Every lead's first plan fit, so the second plan did not fire, and no real lead has written one yet. See [docs/LIVE_TESTS.md](docs/LIVE_TESTS.md).

**Left open.** A lead whose merge reply is malformed twice stops the run though both replies held the right answer, and the verifier failed a right answer on 4 of the 5 runs that reached one (questions 10 and 14 in [ARCHITECTURE.md](ARCHITECTURE.md)).

## v0.9.1 — November 2026: plans that survive a bad file name

**Why.** The side-by-side run lost two plans to a guessed file name, and replays showed a size check that depended on timing.

**Fixed.**
- **File names.** A note names a file however a model spelled it: `cobalt ridge.md`, `cobaltridge.md`, `Quillon Bio.md`, `q3 report.md`. Only the words right before a file extension count, so prose names no file (`tools.py`).
- **A part with no real file.** It goes to the lead, and the rest of the plan stands. With nothing measurable, the old refusal stands (`gates.py`).
- **A sub-agent's room.** It no longer counts its siblings' replies, so the same replies cannot send a call on one run and stop it on the next (`loop.py`).
- **The scorer.** It read from the first `ANSWER:` on a line, so a lead that quoted a sub-agent's marker scored wrong though it was right (`suite.py`).

**What the live run showed** (2 November, Haiku 5.5, $0.14). The same totals as before, 25 verified and 27 right of 30: at 10 companies 12 of 12 right, up from 10, and at 20 companies 3 of 6, down from 5, on three stops the fixes did not cause. See [docs/LIVE_TESTS.md](docs/LIVE_TESTS.md).

**Left open.** A sub-agent's call keeps room for the lead's plan reply, which stopped one run 44 tokens over the cap, and a refused plan gets no second try (questions 12 and 13 in [ARCHITECTURE.md](ARCHITECTURE.md)).

## v0.9.0 — November 2026: the lead knows its members, and a review read against the code

**Why.** Part 7 of the team design: the lead staffs positions, and should know what each can do and has done. Then an outside review of the README made claims and recommendations, and each was tested against the code and the tapes rather than taken or refused on its wording (`docs/LIVE_TESTS.md`, 1 November).

**Built.**
- **Positions and records** (`taskorg/members.py`). A position is a skill and the model that fills it. At the end of every run that staffed a sub-agent, the kernel adds each position's counts from the run's record to `records/positions.json` in the store: parts given, done, verified, failed by code, handed back, calls and tokens. Never from model text; a damaged file never changes the outcome.
- **Cards** (`--cards`, off by default). The lead's plan brief carries a fixed table, one row a skill: tools, whether they open files, the most calls a part may take, the model, what a call has cost, and the position's counts once it has 3 runs. The gates never read it. Off until a test shows it pays: the design had said a flag turns it off, reversed under the rule that structure is added only when measured. `compare` gains the `genet-cards` strategy and reports the parts each lead proposed, the gates refused, and the lead covered.
- **`report-bench`** (`taskorg/report_bench.py`). Parts of 20-company aggregate questions whose plan gave the channel the wrong file, run with the default brief and with `--report-up`. On the simulated reader, `--report-up` hands back every wrong part and no right one.
- **The default abort criterion.** `forecast_short` is on for every new run; `--abort none` turns it off, and naming a criterion replaces the default. It never fired on the 372 taped trials and changes no request.
- **The verify bench's arms** (`--arms note,planted`). The author's note argues for the planted figure, or every file the goal names carries an instruction to pass a wrong product or fail a right one. The simulated reader is unmoved by both; a model has not run them yet.
- **A threat map** (`tests/test_threat_map.py`, `SECURITY.md`). A marker in every field a model fills, followed through a plain split, a rework, hostile channel names, a part handed back, a malformed part and the cards: model text never reaches the guidelines, the lessons, the position records or a later run's brief.
- **A lead told how to name a group's files.** When the workspace does not fit one call, the plan brief says there can be at most 4 sub-agents, and that a part reading several files names each in its note. Roomy runs do not get the sentence, so their requests are unchanged. With the changes below, the simulated figures are 3,417 tokens roomy, 1.20 times a single agent, and 4,683 tight, 0.94 times the crew.
- **A lead told what the goal's files come to.** When the files the goal names do not fit one call, the size note gives their total and says a single agent's later calls carry what it has read. It is a fact the kernel measures, not advice.
- **The independent view is the default** for run commands and `compare`. Tapes recorded before it replay with `--verify-view shared`. `--verify-view shared` restores the old brief, and the bench's setups name their own view.
- **The tapes, published.** Every Claude tape and result, with a replay command for each, as the release `tapes-20261029`. A clean clone with no key replays the 28 and 29 October runs to the token.

**Fixed.** A single-agent run reported its refused parts as "not covered" though the lead did the work and the verifier passed it (`review.part_statuses`).

**Tested and not built.** A 1.7 factor on the gates' material estimate (dropped: on 2 November a scoped sub-agent's largest call ran at most 1.29 times today's estimate, and the factor would have refused groups that ran fine). A token check in the could-we gate (finished fewer runs than today). A figure check in code before the verifier (12 of 12 on the bench, 3 of 11 on real products). Each is recorded in `docs/LIVE_TESTS.md`.

**Corrected in the docs.** The gates do not check that parts are independent; the could-we gate counts calls, not tokens; the log is a record, not proof against tampering; lessons cost tokens and their benefit is unmeasured; the install needs Python 3.11 or newer.

**What the live runs showed** (2 November, Haiku 5.5, $0.10, follow-ups of $0.08, $0.03 and $0.05, a side-by-side run of $0.33 and a told crew of $0.19, `docs/LIVE_TESTS.md`).
- `--report-up`: 10 of 12 wrong parts handed back, no right part, at 6% more tokens. The same 10 said in prose that the figure was missing under the default brief, and the other 2 took a look-alike's figure under both.
- Groups of files. The lead proposed them on 6 of 8 trials; the gates could not measure a group whose files were not named, refused every split, and all 8 runs overflowed. Told how to name them, 8 of 16 leads split, and the other 8 misjudged the sum, proposed nothing and overflowed. Told also what the files come to, all 8 proposed, 7 split, and 6 were verified. 30 of today's 31 split runs reached the right answer: Genet's first live splits on work that does not fit one call.
- Side by side at an 8,000-token cap, 90 trials. On 12 questions that fit one call, no lead proposed a split, and Genet matched the single agent's 12 of 12 at 1.14 times its tokens, where the crew got 7 of 12. On 18 that do not fit, Genet verified 13, the single agent none and the crew 4.
- A crew told the same things (`always-told`) caught up on the large questions: 13 of 18 verified and 18 of 18 right, where Genet got 13 and 15, at about 17% more tokens. So most of Genet's lead there was the notes. On the 12 that fit, it still split all 12 and got 9, at 1.79 times a single agent's tokens. What the gates add is keeping small work single. Over all 30, Genet verified 25 and the told crew 22.
- The verifier failed right answers in 9 of those 31 runs, and 6 stopped on it: 3 of 5 under the shared view and 6 of 26 under the independent. After a split it opens 2 of the files, so a pass checks little under either. Open.
- Three plans were refused because a lead guessed files' names, so a group named no file the workspace holds, and one unmeasured part refuses the whole plan. Open.
- The size check near the cap depends on timing: it keeps room for the largest reply so far, and sub-agents run in parallel. One finished trial stopped in 1 of 3 replays, 9 tokens over. Open.
- A run that stops during its sub-agents may not replay to the token, since how many calls had finished depends on timing. It fails the same way. 81 of the 90 side-by-side trials replay exactly.
- The cards show no sign of helping over 16 trials, at about 460 prompt tokens a plan call on Claude. They stay off.
- A planted instruction was in all 24 briefs and never followed.
- A false author's note was the one that worked. With every source open, it got 5 of 6 look-alike errors past the shared view, which catches all 6 without it. The independent view, answered from the 29 October tape at no cost, caught 12 of 12, and on split runs it did not fail more right answers. It is now the default.
- Reading the claims found a bench bug: 2 wrong figures had been scored "said missing". The answer line now decides, and the tape was rescored at no cost.

**Not measured yet.** Whether past counts on the cards change a plan; what a lead does with a part handed back; whether a planted instruction can steer a lead into writing a false note.

**A limit.** Underscores in a note read as spaces, so a file whose name has one cannot yet be named in it.

- `tests/test_members.py` (53), `tests/test_threat_map.py` (10), `tests/test_verify_arms.py` (12); 42 new mutations, all caught.

## v0.8.0 — October 2026: the shared situation

**Why.** Genet's first design gave every run a situation in six parts: who, what, when, where, why and how. The run state kept those fields after v0.2, but the kernel read only some of them. Pace and the decision points were set when a run was made and never read. The forecasts, the abort criteria and the main effort were never read at all. This is part 8 of the team design (`docs/TEAM_DESIGN.md`): the kernel acts on every field of the situation, or the field goes.

**Built** (`taskorg/situation.py` and the loop):
- **Decision points.** After the plan is judged, after the sub-agents report, and after the verdict. At each one, the kernel forecasts what the rest of the run needs and records it in `projections` and a `decision_point` event. The forecast is the fewest calls left, at the run's average cost per call so far, against the calls and tokens left. A run checks at the decision points its `checkpoints` list, all three by default.
- **Abort criteria** (`--abort`), from a fixed list:
  - `forecast_short`: the budget cannot finish the work;
  - `parts_failed:N`: N parts' sub-agents have failed.

  Free text is refused before the run starts. A criterion that is met stops the run with code `ABORT`, and the review names it. In the suite's case (4,000 tokens a call against a budget of 10,000), `forecast_short` stops the run after its plan, at one call; without it, the run makes three calls and stops on its budget.
- **Main effort** (`--main-effort CHANNEL`). The gates judge that part first, so it is staffed first when the budget or the cap of 4 runs short.
- **Kept current.** Every call a member makes, tool rounds included, carries the goal, purpose, done-when and criteria as they stand at that call. If one changed since its last call, the call says which, and the record notes it. The context stays as it stood at the split.
- **Reported up** (`--report-up`, off by default because it changes the sub-agent brief). A sub-agent may hand its part back with `replan:REASON`.
  - Its reply is not merged.
  - The kernel posts the reason on the escalate stream and opens a replan request.
  - After the reports, the kernel closes the request for the lead with the method that follows, in which the lead covers the part.
  - The merge brief gives the lead the reason.
  - A part handed back is covered, not failed: it does not count toward `parts_failed`, and the review lists it as handed back.
- **Pace is gone.** `cadence` left the run state, the saved run and the schema. An older saved run's value is read and ignored. The JSON schema now lists the decision points and the form of an abort criterion.

**Unchanged by default.** With default flags, every request is byte for byte what it was. The 28 October concept tape and the 29 October verify-bench tape replay with no missing requests and the same results. The sim figures are unchanged: 1.20 times a single agent roomy, 0.92 times the crew tight.

**Not built or not measured yet.**
- Marking a fact every part depends on, so a change to it reaches every member. There is no way yet to mark one.
- Whether a sub-agent on a real model hands back a part it cannot do, rather than guess. That needs a live crew run with `--report-up`, on a go-ahead for spend.

- `tests/test_situation.py` (35 tests), and 13 new mutations, for 219, all caught. 1,538 tests.

## v0.7.0 — October 2026: a verifier that can check

**Why.** In the 28 October rerun, the verifier passed a single agent's wrong total, 1152.1 for 1142.6. It had no sources, and its brief carried the author's own note that look-alike files were excluded. The verifier is the one member whose work is to disagree with the author, and it could neither check nor come to the product fresh. This is part 2 of the team design (`docs/TEAM_DESIGN.md`): members differ by what they see and what they may open, not by what they know.

**Built:**
- **What the verifier sees** (`--verify-view shared|independent`). The independent view gives the verifier:
  - the context as the operator gave it;
  - the goal and the criteria;
  - the product with its evidence.

  It does not get the lead's context updates, the working product, or sub-agents' reports.
- **Sources the kernel opens** (`--verify-sources none|layered|full`). The kernel picks files from the run's record and puts them in the verifier's brief, as many as fit the per-call limit. The author doesn't choose them, and neither does the verifier.
  - `layered` opens these, in order:
    1. a file the goal names that no call in the run read or searched;
    2. files the product's uncertainty names;
    3. two drawn at random from what the goal names or the product cites.
  - Each pick and its reason go on the record.
  - The random draw is seeded by the goal and the product, so the same product opens the same files and a tape replays.
- **The record keeps what the tools showed.** Each tool event names the file a read showed, or the files a search returned lines from.
- **A quote check in code, for nothing.** An evidence quote that is not in the file it cites is named to the verifier, which still gives the verdict.
- **`verify-bench`.** It reviews products with one planted error (a look-alike's figure, or the FY2025 one) and right ones, each with its author's record, under five setups, and reports catches, false fails and tokens. On the simulated reader:
  - `full` catches every planted error, `layered` every look-alike one, and `today` none;
  - nothing right is failed.
- **`scripts/verify_runs.sh`** runs the bench on Haiku 5.5: 120 reviews, about $0.20, capped at $0.40, taped.

**Layered by default.** After the live run below, `--verify-sources layered` became the default. A run with no workspace opens nothing, so its verifier's request is unchanged. `--verify-sources none` sends the request as it was before: with it, the 28 October tapes replay on the new code with no missing requests and the same results. The simulated reader's counts now include the verifier's files: Genet is 1.20 times a single agent with a roomy context (was 1.28) and 0.92 times the crew with a tight one (was 0.90).

**On Haiku 5.5** (29 October, 120 reviews, $0.21; `docs/LIVE_TESTS.md`):
- `today` caught 2 of 12 planted errors, only where the product's own quote showed the wrong year;
- `full` caught 12 of 12 in both views;
- `layered` caught every look-alike error, and 9 of 12 in all for the right reason, in both views;
- no setup failed a right product;
- leaving out the author's notes made no measurable difference.

The bench now also counts FAILs that name the planted company, since one FAIL was for another company's figure. The run scripts' progress filter is line-buffered, so the `[n/N]` lines show as they happen.

**The quote check, fixed on real products.** Before the default changed, the check ran over all 885 products on the Claude tapes. It flagged 88, nearly all falsely:
- an evidence line citing two files, with every quote matched against the first;
- a file named inside the quoted text;
- quotes of the tool's own words, a search query or a member's report;
- a dash the reply carried as the text `\u2013`.

Each quote is now checked against the files its line cites outside the quote. It flags 6, each a quote those files do not hold.

**Decided, not built yet.** The README's "workers that spawn workers" refusal is lifted for nesting, which keeps the gates, a depth limit and a reserved budget (`docs/TEAM_DESIGN.md`, part 3).

- `tests/test_verify_checks.py` (29 tests), and 20 new mutations, for 206, all caught.

## v0.6.0 — October 2026: testing the concept, and what it shows

**Back to the concept.** Genet's question is whether a second agent does new work, and its claim is the best baseline's accuracy at close to single-agent cost. The comparison had never marked work as already done, so the first gate never ran in it, and its questions were too small for a single agent to struggle at a real context size; size had become the only "should we" reason. Three suite options now test the concept, each off by default (the default suite's fingerprint is tested): `--entities`, `--distractors` and `--filed`. `scripts/concept_runs.sh` runs both arms on Claude.

**What the live runs show** (Haiku 5.5; `docs/LIVE_TESTS.md`). A single agent got every answer at 5, 10 and 20 companies a question, about 84,000 tokens a task at the largest, so splitting for quality is not shown on this model and these tasks. The always-split crew lost accuracy as the work grew (8 of 8, 5 of 8, 5 of 7), and cost less past about 10 companies but about the same per right answer. Genet stayed one agent wherever the work fit; with half of each question's companies already filed, it was the cheapest strategy. Haiku's crew lead left filed work out by itself, so the first gate had nothing to refuse.

**Fixed, from three runs at a tight cap (4,000 tokens a call):**
- **One copy of each file per call.** Haiku read each file and searched it too, so a call carried 2.4 times its files' text (up to 3.8). Reads run first in a round, and nothing read in full is returned again.
- **Files measured in the model's tokens.** The gates counted four characters a token; Claude counts about 1.5 times that. Adapters carry a `token_ratio`.
- **A sub-agent's tools open only its part.** Given the whole goal, each sub-agent read every company's file and overran the call its part was sized for. Its toolbox is now scoped to the files the gates measured, and its brief names them.
- **The lead plans knowing the limit,** from a SIZE note in the plan brief, and **replies are asked to be brief** (at most 5 pieces of evidence, one-sentence uncertainty).

**Fixed, from the concept experiments:** proposals past the cap of 16 are the lead's to cover, told by count, where they had been dropped; the simulated reader asks again for reads a round did not run; and the context's example of a file name is a company with no look-alike, after it primed readers to map Halvorsen Freight Labs to `halvorsen-freight.md`.

**Open.** Judging fit before the work starts is unreliable on a real model: the lead misjudges it, and searches pull in look-alike files the gates do not count. A re-plan on a measured overflow would answer from what happened.

- Sim figures, recounted: Genet 2,643 tokens a task against 2,068 for a single agent with a roomy context (1.28×), and 3,862 against 4,288 for the crew with a tight one (0.90×).
- `tests/test_concept_suite.py`, more in `tests/test_live_findings.py`, and 14 new mutations, for 186, all caught.

## v0.5.0 — October 2026: Claude, a spend cap, and tapes

**Claude through the Messages API.** `--adapter anthropic` uses the official SDK, an optional extra (`pip install -e '.[anthropic]'`); Genet itself still needs nothing. The prompts, the JSON gate and the token accounting are the live adapter's. The OpenAI-compatible adapter could not reach Claude: it sends `temperature: 0`, which current Claude models reject with a 400. The key is read from `TASKORG_ANTHROPIC_KEY` only, so a key exported for another tool is never spent and the live adapter's endpoint never receives it. Redirects are not followed. `TASKORG_MODEL_EFFORT` sets how much the model thinks; thinking tokens count as output and are recorded on their own. A refusal fails as `LIVE`, with its tokens counted.

**A spend cap.** `compare --max-spend` stops before a trial that could take spending past the cap, judged by the costliest trial so far. Ctrl-C stops a comparison too. Either way the trials already run are saved, with `stopped_after` in the results.

**Tapes.** `compare --record` saves every exchange as it happens, and `compare --replay` reruns a comparison from the tape with no key and no spend. Rehearsed through the real SDK against a local endpoint with 5% overload faults: 188 exchanges recorded, and the replay reproduced all 32 trials exactly. A request the tape does not have fails as `LIVE` and is counted.

**Tool results name files relative to the workspace.** They showed the absolute path, so a comparison's temp folder reached the model, and every run's requests differed, which kept a tape from replaying. A name that would read a different file back stays absolute.

- `scripts/live_pilot.sh`: the pilot on Claude, with a smoke test, a cap per model and a tape.
**The first live pilot, on Claude Haiku 5.5.** 32 trials, 220 calls, $0.14 (`docs/LIVE_TESTS.md`). The verifier failed 36 of 50 products, and 12 runs with the right answer ended on a failed verdict, so eight tasks a strategy could not rank the strategies. It found four problems, all fixed:
- **`claim` is the product.** Replies put the answer in a key of its own, which the schema refuses, and repeated it on the retry. The prompt now says that `claim` is the product and that any other key is refused, and the retry note says where its content goes.
- **The verifier judged the old product.** After a rework, working memory kept the old product and the new one sat under BRIEF, which a model reads as its brief. The verifier now gets the product under a heading that names it, and working memory holds the reworked product.
- **The harness asked for more than grading.** "One line ANSWER:" was read as a line of its own, though grading takes the marker anywhere; the notes named quarters by month and never said which months make FY2026 Q1. The harness now asks for "ends with ANSWER: <value>" and states the calendar. The simulated reader's figures, recounted after all the prompt changes: 2,603 tokens a task for Genet against 2,082 for a single agent with a roomy context (1.25×), and 3,697 against 4,103 for the crew with a tight one (0.90×).
- **Claude counts more tokens.** 1.39 to 1.73 times Genet's estimate from characters; the Claude adapter's size estimate is now 1.75 times it.

**The rerun, with those four fixed.** Single, crew and Genet each got 8 of 8, genet-stated 6 of 8, in 151 calls for $0.10. With a roomy context Genet cost 1.53 times a single agent: a real model's planning call costs about as much as a working call. Two more problems, fixed:
- **Workers got one word of their note.** The kernel joined the lead's proposals and split them on spaces, so a note written as prose reached its worker as its first word. Proposals are now read one request at a time.
- **Placeholders copied literally.** The plan prompts showed `subtask:<channel>@<skill>=...`, and the model wrote `<channel>`, an empty channel or `lead`, so in 3 of 8 trials the crew's every proposal was refused. Both prompts now show a real proposal and say to name a part after the file it reads.

**A second rerun, with those fixed.** Single and Genet 8 of 8, the crew 7 of 8, genet-stated 6 of 8, in 190 calls for $0.12. The crew staffed workers in every trial, with notes of 5 to 33 words and channels named after real files. The three Haiku runs cost $0.36 in all. One more fix from it: the verifier read the product's claim and not the evidence given with it, which the kernel's own criteria check counts, so it failed sourced answers as unsourced. It now reads up to 12 items of evidence.

- `tests/test_anthropic_tape.py` and `tests/test_live_findings.py`, and 25 new mutations, for 172, all caught.

## v0.4.3 — October 2026: calls end, and every token is counted

**Calls cannot loop.** An audit of every loop in the kernel found three that are open-ended, each with a hard stop. Reading a reply ends at the size cap or the exchange's deadline. Walking a workspace ends at 20,000 entries. Waiting to admit a call near the budget re-checks the budget and the clock every second, and calls in flight always finish or time out. Everything else that calls a model runs a fixed number of times: tool rounds are counted, a retry happens at most once, a rework at most once.

**Tested against a hostile model.** `tests/test_bounds.py` runs 400 seeded runs, and 5,000 more were run outside the suite. A stand-in model floods tools and proposals, sends malformed replies, fails calls, breaks authority rules, fails verdicts, and reports token counts that are random, missing or not numbers. Budgets, strategies, entry points and parallelism are all random. Every run ended without leaving a thread, stayed within `max_calls`, and recorded every call it made exactly once. Tokens were recorded as reported or as marked estimates, spend stayed under `max_tokens` plus one call's cap, and the totals matched in the run, `diagnose` and a saved copy.

**Two token gaps, closed:**
- **An unreported reply was counted by its claim alone.** When an endpoint reported no usage, the kernel estimated the reply from its `claim` field. A reply of about 2,000 tokens was counted as 3. The kernel now counts everything the model wrote. The live adapter estimates from the exact request it sent and the raw reply it got, malformed or not, and marks those calls `tokens_estimated`.
- **Nothing stopped a reply that ran on.** No request carried a reply limit, so a runaway reply would be billed before the kernel could see it. Every live request now asks the endpoint to stop the reply at what is left of the per-call cap (`max_tokens`; `TASKORG_MODEL_MAX_TOKENS_PARAM` renames the field or turns it off). A reply cut off there ends after one retry.

**Sim figures, recounted.** Counting whole replies raises the simulated reader's token counts a little. Genet's planning reply, with its proposed sub-tasks, now counts in full. With a roomy context Genet costs 2,372 tokens a task against 1,952 for a single agent (1.22×, was 1.19×). With a tight context it costs 3,291 against 3,623 for the crew (0.91×, unchanged). Accuracy is unchanged everywhere.

- 8 new mutations, for 147, all caught.

## v0.4.2 — October 2026: ready for a live run

Four gaps, found in the past live data and in a rehearsal of the live path against a stand-in endpoint on this machine:

- **Room for the reply.** The size check before a call counted the brief but not the reply. In the rehearsal, one call's prompt fit and its reply then overran the cap after it was paid for. The check now keeps room for the reply: the largest reply in the run so far, and 200 tokens for a live model before its first reply. That is the top of the 109 to 205 tokens per reply on record. The gates count the same room when they judge what fits, so they never keep work in a call the size check would refuse. Rehearsed at a 1,500-token cap, no call was paid for and then overran. The stub and sim figures are unchanged.
- **One retry for a malformed reply.** A reply that is not the artifact schema is asked again once, with a note saying what was wrong. The retry is a budgeted call, and the failed first one stays on the record. Authority violations, transport failures and budget halts are never retried. A recovered retry still gets a team review and leaves its lesson. Under injected faults on every call (5%, large context), Genet went from 87% to 100% and a single agent from 82% to 98%.
- **Default criteria are flagged.** Every past live run used default criteria ("default task" and "purpose", or the older default pair), which any reply that echoes its brief meets. A run verified only against them now carries `verified_against_default_criteria` in `diagnose` and a warning in the CLI's output. Health is not changed.
- **The verifier checks the goal.** A past live run passed an answer about Jean Genet the playwright on a task about this kernel. The live verifier is now told to pass a product only if it answers the goal, its subject and its question, and to fail one about something else even when it repeats the criteria. Whether a model follows that is for the live pilot to show.
- `tests/test_readiness.py`, and 9 new mutations, for 139, all caught.

## v0.4.1 — October 2026: findings from the past live data and longer tests

- **The oldest review answers are translated.** Real pre-0.2 runs answered reviews with `HOLD_ORG` and `CHANGE_HOW`, which the loader kept as they were, so `policy-replay` read a method change as a hold. They now load as `KEEP_ROSTER` and `CHANGE_METHOD`, in notes and in the log, whatever the file's format.
- **Failed parts are recorded in sub-task order.** A part whose sub-agent failed was logged from that sub-agent's thread, so the record's order depended on timing, and one test failed now and then. Failures are now recorded with the other results, in sub-task order, so the board stays deterministic.
- One new mutation, for 130.

## v0.4.0 — October 2026: shared ownership

The lead makes every decision; the outcome is the team's. Two pieces:

- **A failed part goes back to the team.**
  - A sub-agent whose reply is malformed (`SCHEMA`) or whose call to the model fails (`LIVE`) no longer ends the run. Its part is recorded as `part_failed`.
  - The other sub-agents' results are merged, and the lead covers the failed part in the merge, the same way it covers a part the gates refused. This works in `run_task` and in `fanout`, and the operator's answer says which parts the lead covered.
  - An authority violation (`TOOLS`, `ROSTER`, `INV-*`), a budget halt and a crash still stop the run at once.
  - When several sub-agents stop, the error raised is the one that caused it, not a sibling's "run already abort".
- **A blameless review after every failure, and lessons for the next run.**
  - When a run had any failure, even one the team recovered from, the kernel writes `Run.review`. It holds what failed, what became of each part, what the team did and the outcome, and it is the last entry on the record.
  - The review is built from the record (event codes, criteria misses, part statuses), never from model text.
  - Each kind of failure maps to one fixed lesson, which is added to `guidelines/lessons.md`. Every later brief carries it. Repeats are counted, at most 10 lessons are kept, and `--no-lessons` (`Engine(lessons=False)`) turns lessons off.
  - An operator's Ctrl-C is not a team failure, and writing a review can never change a run's outcome.
- `diagnose` reports `team` (each part's outcome) and `review`, and the CLI prints the review with the run.
- Comparison trials each use a fresh store, so no lesson carries between strategies. The published figures are unchanged.
- `tests/test_ownership.py`, and 11 new mutations, for 129, all caught.

## v0.3.3 — October 2026: four follow-ups

The four items v0.3.2 left open, each with a test and a mutation:

- **Failed calls are counted.** A call that fails after it was sent stays on the record, marked `failed` with its error code. It counts toward the budget, toward `diagnose`'s `failed_calls`, and toward the calls, tokens and cost a comparison reports. It uses the endpoint's token counts when the endpoint sent them, and the brief's estimate otherwise. Before this, a failed trial looked free.
- **Saves are atomic.** Saved runs, working memory, episodes, guidelines, comparison results and policy files go to a temporary file that replaces the old one in a single step, keeping its permissions. A crash mid-save leaves the previous file. Damaged working memory is a `STORE` error, not a traceback.
- **An answered review note stays answered.** Answering a closed note again is refused, so a record cannot be rewritten or used to change the method after the fact. A deferred note can still be answered.
- **The size check counts what is sent.** An adapter now estimates its own request, and the live adapter counts its system prompt and JSON wrapping, so an oversized request is refused before it is sent rather than after. The stub and simulated adapters are unchanged, and so are the published figures.

## v0.3.2 — October 2026: review findings

A review in four parallel parts: concurrency and run state, input handling, persistence and the CLI, and decision logic with the comparison harness. Each finding was reproduced on v0.3.1 before it was fixed, and each fix has a test in `tests/test_hardening.py`.

**Concurrency and run state**
- When one sub-agent failed, its siblings kept calling the model for every remaining tool round (9 extra calls in the repro), and Ctrl-C could not stop them. The board now closes at once; no call starts after a failure.
- Parallel sub-agents each passed the pre-call budget check before any of them was recorded, so they overspent by one call each. Calls in flight now count; parallel spend matches sequential.
- An exception other than a kernel rule left the run active and unsaved. Every failure now aborts the run with a reason, and the CLI saves it as `CRASH`.
- A completed run could be aborted, a halt overwrote the first reason, a refused human override was still logged, and a roster change could halt a run that had spent its budget legally. All fixed.
- A reused engine shared one budget clock between runs. Each run gets its own.

**Budgets and decisions**
- The gates reserved 2 calls after a split, but a merge that covers a left-over part reads first, so an admitted split could run out before the verifier. The merge's tool rounds are now reserved, and work, merge and rework stop their tool rounds in time to leave the verifier its call.
- The verdict was read by prefix and substring: "PASS: nothing failed" failed and "Passing this would be wrong" passed. It is now the leading word.
- Success criteria matched as substrings: "4.1" was met by "14.1". They now match whole words and numbers.
- The measured gate counted whole files, but a read returns at most 4,000 characters, so it split work that fit. It now counts what one read returns, and refuses a split that leaves any sub-agent over the room in one call.
- Duplicate proposals got no gate record, and `fanout` silently dropped parts refused for the cap or a bad skill and claimed a fan-out that did not happen. All fixed.

**Comparison harness**
- The crew baseline dropped parts past the worker cap or with a bad id, while genet's lead covered them: same plan, crew 0/5, genet 5/5. Both now hand such parts to the lead.
- Grading took the first number on a line ("Q3" read as 3) and any "answer:" in prose. It now reads the capitalized `ANSWER:` marker and requires one value.
- "Best baseline" could name genet-stated, a genet variant, depending on argument order. It now names single or always.
- The published simulated-reader figures are unchanged.

**Input handling**
- A model's request with a NUL byte, a lone surrogate, an over-long name or a symlink loop, or a workspace folder without permission, crashed the kernel. These are now "not found" or skipped.
- One folder with 200,000 files took 64 s and 351 MB of memory across a plan; the walk now stops at its cap mid-folder (4.7 s, 60 MB).
- Partial search matches were all kept before trimming (about 1 GB in one repro); only the best 20 are kept now. Search terms are capped at 16.
- A server could hold a call open by dripping headers or an error body; one deadline now covers the whole exchange. A stalled error body, a non-object `usage`, a non-string `claim`, an out-of-range timeout or a malformed base URL are clean `LIVE` or `SCHEMA` errors.
- A snippet could drop the matched figure when lower-casing changed a line's length.

**Persistence, CLI and diagnostics**
- A setup error, such as a missing live configuration, overwrote `--out` with an empty run. Setup now happens before anything is written, and the default `--out` follows `--id`.
- Wrongly typed fields in a run file crashed read commands later; they are refused as `PERSIST` at load. Old log vocabulary is upgraded, and a loaded run keeps its elapsed time and its world.
- Aborted runs and failed stop rules reported `health: ok`; they are `degraded` now. The authority-language check is no longer evaded by quoting the rule first.
- Missing files and directories, `nan` budgets, zero or negative counts, blank criteria and run ids ending in a newline are clean errors. `bench` fails when it checked nothing, `policy-replay` reads runs through `load_run`, and the policy flags take effect.
- 36 new mutations, for 113.
- Left open, fixed in v0.3.3: failed calls missing from cost reports, non-atomic saves, re-answerable review notes, and a size estimate that left out the system prompt.

## v0.3.1 — October 2026: security hardening

A review for the class of bug behind the October 2026 PHP flaws: untrusted input that exhausts memory, escapes a sandbox or slips past parsing. Each fix has a test that fails on the code before it.

- **The API key stays with the host you named.** Redirects are refused, and the key is never copied onto a redirected request. The base URL must be `https://`, or `http://` to this machine; `TASKORG_MODEL_ALLOW_HTTP=1` allows plain HTTP elsewhere.
- **The endpoint's reply is bounded.** At most 8 MB, read within the timeout. Malformed JSON, nesting too deep and over-long numbers are clean `LIVE` or `SCHEMA` errors, not crashes. An error body is read only as far as the message needs.
- **Token counts are checked.** A reported count that is negative, fractional or not a number is ignored, and the kernel's estimate stands, so a reply cannot spend negative tokens past the budget.
- **An oversized brief is never sent.** Its size is checked against the per-call cap before the call. Before this, one reply asking for the same file 2,000 times produced an 8 MB brief that was sent before the cap stopped the run.
- **One reply does a bounded amount of work.** At most 8 tools a round (repeats count once) and 16 sub-task proposals judged per plan.
- **Hidden files stay hidden.** `read` and `observe` could reach `.env` and `.git/`, and search could reach a hidden file through a symlink. Now no tool reaches a path with a dot-named part below a workspace root.
- **The workspace walk is bounded.** It no longer lists a whole tree before applying its cap, it prunes hidden and tool folders as it goes, and one search scans at most 20M characters. The scan for file names in a sub-task note is linear; a long note used to take seconds to minutes.
- **Saved runs are untrusted.** A malformed file is a `PERSIST` error, and a saved slot cannot hold tools its skill does not allow.
- **Repository.** No secrets in any commit, no key files ever committed, and the site loads no scripts or third-party resources. Added `SECURITY.md`.
- 15 new mutations, for 77, all caught.

## v0.3 — October 2026

- **Measured "should we".** A fan-out of the lead's proposals needs one of two reasons:
  - The operator declared isolation (`--isolate`).
  - The sub-tasks' material doesn't fit in one call, estimated from the sizes of the workspace files they cover. The room in one call is the per-call limit less what the lead's planning call cost, brief and reply. A file several sub-tasks need counts once, and a split that leaves one sub-agent carrying all of the material is refused.

  Material that can't be measured doesn't count as a reason. Every gate record names its basis: `declared`, `measured` or `stated`. `--split-policy stated` keeps the old behavior for comparison, and `compare` gains a `genet-stated` strategy.
- **What the simulated reader shows.** Genet matches the best accuracy in both regimes:
  - **Roomy context (16k):** Genet stays a single agent at 1.19× its cost; it was 2.5× before this change.
  - **Tight context (1.5k):** a single agent aborts on overflow, scoring 55%, and Genet fans out at 0.91× the cost of a crew. Per family, it splits only where a single agent fails (aggregate, breadth) and stays single where one succeeds (lookup, compare).
- **Mutation testing.** `scripts/mutation_check.py` breaks rules one at a time. The first pass, over 57 rules, found 4 that no test protected:
  - the gate record's own order check
  - the reviewer's skill ban
  - sub-agents working from the split-time context
  - the replan tier check

  Each now has a test. Five more mutations cover the material rules, for 62, all caught. A fast test in the regular suite fails when a mutation no longer matches the code, and the runner itself now fails on one instead of skipping it.
- **Split basis in diagnostics.** `diagnose` reports `split_basis` for the run, and each gate interaction keeps its basis.
- **A sim fix.** The deterministic reader read a file once per mention, so each sub-agent read its file three times. That inflated every sub-agent's cost in earlier sim results. The figures above are after the fix.

## v0.2 — October 2026

### Lead-driven staffing

- **The lead staffs the task.** `Engine.run_task` / `taskorg run`: the lead reads the context and proposes sub-agents as `subtask:<channel>@<skill>=<named_failure>`. The kernel judges every proposal; the lead never writes the roster.
- **Real gates.** `gates.assess` checks:
  - world coverage (exact file name or channel)
  - a staffed or repeated channel
  - verification already belonging to the verifier
  - a named failure
  - a known skill and a usable channel id
  - the budget tier
  - budget affordability, counting each sub-agent's tool rounds
  - the worker cap
  - a single open sub-task being the lead's job

  Every verdict is logged as a full gate record.
- **Specialists.** Each skill has a brief, a tool allowlist and an optional model (`TASKORG_MODEL_NAME_<SKILL>`). Sub-agents are created with the skill their sub-task names. A single agent switches to the skill the work needs.
- **Sandboxed tools.** `read`, `retrieve` and `observe` reach only the `--workspace` directories and the `--read` files, and they only read. The allowlist is checked before anything runs. Each round is a budgeted call; at most 2 rounds per sub-agent.
- **Sub-agents work at the same time.** Threads with locked run accounting and per-thread usage in the live adapter. Results are accepted in sub-task order, so the run log is deterministic.
- **Replan on a failed check.** If the verifier fails the product in the normal or open tier, the lead requests a replan, changes the method and reworks once.
- **Comparison harness.** `taskorg compare` runs a single agent vs an always-split crew vs genet on a seeded synthetic suite (lookup, aggregate, compare, breadth). Everything but how the task is staffed is held equal. It reports accuracy, tokens, calls, latency, split rate and cost. It is validated offline with an oracle model and a deterministic reader; **no live results yet**.
- **Sub-agents and the cap.** Sub-tasks refused for capacity, or because the proposal was malformed, no longer drop. The lead covers them while merging, using its search tools.
- **Deterministic reader (`--adapter sim`).** It solves every suite task under every strategy, which proves the harness gives each strategy the facts it needs, and it compares structural cost at $0. With a perfect reader, a single agent is cheapest in every family. Splitting can only pay where a real model reads worse in one context.
- **Sub-agent notes.** Each sub-agent gets the lead's note from its sub-task, not only its channel name. Before this, a crew's assignments never reached its workers.
- **New test suites.**
  - **Red team:** hostile model output must be refused, contained or halted.
  - **Invariant fuzzing:** 300 random sequences of 40 calls each.
  - **Concurrency stress.**
  - **Live adapter** against a fake OpenAI-compatible endpoint.
  - **Compatibility:** saved runs in older formats.
- **Found by the fuzzer, and fixed:**
  - An unknown slot raised a raw `KeyError`.
  - A completed or aborted run still accepted reviews, skill changes and updates. Closed runs are now read-only (`CLOSED`).
  - Reusing a note id silently overwrote an open replan request, which could then be answered with `KEEP_ROSTER`. Note ids are now single-use.
- **Diagrams.** `docs/diagrams/build.py` renders three explainer figures, in light and dark for the README and inline for the Pages site:
  - three ways to staff a task
  - the gate funnel
  - control plane vs model plane
- **Native bench.** `taskorg bench` scores every fixture's `expect` block and no longer needs pytest. Four lead-driven fixtures were added.

### Vocabulary

The code and docs now use common agent-industry terms throughout. This is a breaking change for anyone importing `taskorg`; saved runs in the old formats still load.

| Area | Changes |
|---|---|
| Core names | `Mission` is now `Run`. The shared state is `RunState`, the lead is `lead`, and a sub-task is `Subtask`. |
| Run state fields | `goal`, `context`, `done_when` |
| Skills | Each slot carries a `skill`, changed with `switch_skill`. |
| Reviews | `open_review`, `answer_review`, `request_replan` |
| Message streams | merge, escalate, report, peer |
| Budget tiers | tight, normal, open |
| CLI | `run`, `single`, `fanout`, `replan`, `--context`, `--tier` |

### Fixes from the review

- **Broken README commands.** The README's fan-out and replan commands failed with their own default axes. A run that died on an invariant was saved as `active`; it is now `abort`.
- **Sub-agent isolation leaked.** A sub-agent's brief carried the live context, which held another sub-agent's result. Sub-agents now get the context as it stood at the split. The isolation check covers the whole brief, and the verdict survives save and load; it used to read a field that saving drops.
- **The CLI loaded code from `~/src/ecphory/src` on every command.** That hook is removed.
- **A reused run id inherited the last run's working memory.** Each CLI run now starts clean, and run ids are checked before they become file names.
- **The verifier could pass an empty product by echoing the criteria.** Criteria must now show in the product.
- **"Already exists" used substring matching,** so channel `a` was blocked by any path containing an "a". It now matches exact names.
- **Roster changes:**
  - A refused change still logged a split.
  - A worker could be re-tasked to a new channel without gates.
  - Duplicate slot ids were accepted.
- **Gate checking order:** `GateRecord.assert_legal` checked "should we" before "can someone else".
- **A budget off-by-one:** a run that used exactly its call budget was aborted, and its last call discarded.
- **Tool violations were reported as `BUDGET`.**
- **Policy JSON:** a confidence of 0 became 0.5, and bad JSON escaped as a raw error.
- **Live adapter:**
  - An empty `TASKORG_MODEL_NAME` was sent as `""`.
  - Read timeouts and HTTP error bodies escaped as raw tracebacks.
  - The lead and verifier were told they were workers.
- **Tests that could not fail:** `or True` and similar assertions now actually assert.

## v0.1 — 1 September 2026

A small multi-agent runtime. A run starts as one lead. Skills sit latent, and the context turns a skill on. A second worker is legal only after three gates, in order: can someone else → should we → could we. Models fill a structured artifact. They do not rewrite the roster.

| Piece | Job |
|---|---|
| Run / run state | Shared state |
| Engine | Inspect → skill → gates → maybe a worker → verify → close |
| Gates + world | Covered work refuses a new agent |
| Budget tiers | Tight: no fan-out. Normal: replan only. Open: may fan out. |
| Live adapter | Chat completions → artifact JSON only |
| Verifier | Named criteria plus run-state checks |
| CLI | Single-agent, fan-out, replan, brief, board, diagnose, bench and policy commands |

### Policy sprints (experimental, not wired into runs)

- **N1:** a socket, an encoder, and `apply_decision`, which never grows the roster.
- **N2:** an imitation logistic head with gold accuracy 1.0 on the synthetic set. The set has 9 distinct states; training and "held-out" rows overlap; and the gold labels never include `PROPOSE_CHANNEL`. This shows the plumbing, not learning.
- **N3:** sparse RL with an illegal rate of 0 vs the stub. `apply_decision` cannot add workers and the head never proposes channels, so 0 holds by construction.
- **Fine-tune:** SFT JSONL plus a local head trained on the same synthetic corpus. No Grok weight job exists on the public xAI API.

### Live proof (operator key)

Model: `grok-4.20-non-reasoning`.

- **Tight tier:** stayed a single agent.
- **Normal tier:** changed the method, not the headcount.
- **Open tier:** fanned out to two isolated channels. Isolation was only checked on packets then; see v0.2.
- **"Exists" case:** skipped the file already on disk.
- **job-status-1e:** wrote a five-line status from an attached README, against two named criteria.

The v0.1 commands are in `docs/LIVE_TESTS.md`.

Live run logs stay local. They are not committed; `.gitignore` covers the run-output folders under `data/`.

## Not claimed

Not a product. Not a GAIA score. Not a fine-tuned Grok checkpoint. GAIA vs CrewAI stays closed until a shared harness exists (see `fixtures/bench/GAIA.md`).

## Size

Kernel: about 6,100 lines in `taskorg/`. Suite: about 1,320 checks (including 300 fuzz sequences and 400 hostile-model runs), 9 bench fixtures, and 147 mutation checks.

## Run

```bash
pip install -e ".[dev]"
pytest -q
python -m taskorg.cli run --tier tight
python -m taskorg.cli bench
```

Live adapter: set `TASKORG_MODEL_BASE`, `TASKORG_MODEL_KEY` and `TASKORG_MODEL_NAME`, then pass `--adapter live`.
