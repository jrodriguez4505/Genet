# Head-to-head plan: Genet against CrewAI on public documents

Status: run on 9 November 2026, $2.85 in all. CrewAI was right on 25 of Loong's 40, Genet on 20, so Genet misses the accuracy bar; it holds the other four. The results and what is behind them are in [LIVE_TESTS.md](LIVE_TESTS.md#9-november-2026-a-head-to-head-with-crewai-on-public-documents). Before the main run had results, "right" on Loong was changed from a judge score of 100 to a score of at least 80, for the reason the calibration gives.

## The question

Genet's claim is the best baseline's accuracy at close to one agent's cost, because an agent is added only when it does work the others could not. Every test so far compared Genet with its own baselines on generated company notes. This one puts it beside an established multi-agent framework, on public questions over real documents, with the same model, tools and budget on both sides.

## The questions

**Main set: [Loong](https://github.com/MozerWang/Loong)** (EMNLP 2024, Apache-2.0). Questions over about 11 documents each, already plain text. We use the English financial reports only: 2024 quarterly and annual filings from the U.S. SEC. Loong's legal cases are Chinese, and its arXiv papers carry no right to redistribute.

- Four kinds of question:
  - spotlight locating: find the one document that answers;
  - comparison across filings;
  - clustering: report integration;
  - chain of reasoning: temporal analysis, where each step needs the last.

  The first three divide across documents. The fourth is the sequential kind that others found multi-agent teams lose on.
- Sets 1 and 2 only, which Loong labels 10,000 to 100,000 tokens of documents a question. The filings themselves are longer than the labels: 240,000 to 517,000 characters a question, a median of 440,000, which Genet's estimate puts at 105,000 to 226,000 tokens. Each question has 2 to 5 filings, mostly 3.
- 40 questions: 10 of each kind, drawn by a fixed seed (`benchmarks.loong_sample`, seed 1108) from the 295 English financial questions, listed before any run: 36 from Set 2, 4 from Set 1. Four more, one of each kind, are the calibration. A question that names one of the 4 companies with two 2024 filings is left out before the draw: Loong's code takes whichever the file system lists first, so its gold answer could come from either.

**Control set: [HotpotQA](https://hotpotqa.github.io/)** (CC BY-SA 4.0), the most widely used benchmark of questions that need two linked passages.

- 20 questions from the dev set's distractor setting, each with 10 short Wikipedia paragraphs: the 2 that answer it and 8 chosen to mislead. That is about 1,500 tokens in all.
- 10 "bridge" questions, which need one passage to find the other (sequential), and 10 "comparison" questions, which set two things side by side (divisible). `scripts/h2h_fetch_hotpot.py` shuffles the 7,405 dev offsets with seed 1108 and keeps the first 10 of each type; it fetched 43 rows to keep 20. HotpotQA's own download server no longer resolves, so the rows came from Hugging Face's dataset service for the HotpotQA team's copy, `hotpotqa/hotpot_qa`.
- One agent should be enough here, so Genet should stay one agent.
- Scored by HotpotQA's own exact-match and F1 rules. Right is an exact match, with F1 beside it.

**Why not a better-known agent benchmark.** GAIA, SWE-bench and BrowseComp are the ones most often cited for agents. Each needs web browsing or code execution, and Genet's tools only read, search and list files, by design. Testing on them would measure tools Genet does not have. Loong is peer-reviewed but less known; it was chosen because it is built around the question Genet asks. GAIA, with web and code tools added to Genet first, is a possible second phase under its own plan.

## The contenders

| | What it is |
|---|---|
| One agent | Genet's `single`: the lead alone, reading in rounds |
| CrewAI | [CrewAI](https://github.com/crewAIInc/crewAI) 1.15.30 (MIT, 24 October 2026), hierarchical process: a manager and 4 reader agents, delegation the manager's choice |
| Told crew | Genet's `always-told`: always splits, given the same size facts as Genet |
| Genet | the lead proposes, the gates decide, the verifier checks |

Four readers for CrewAI match Genet's cap of 4 sub-agents. CrewAI 1.15.30 is the newest release at least two weeks old; it releases almost daily.

## What is held equal

- **The model:** Claude Haiku 5.5, effort low, for every call of every contender. Sonnet only after, on a separate say-so.
- **The tools:** read, search and list over the same folder. CrewAI's tools are thin wrappers around Genet's `Toolbox`, so both get the same text back.
- **The budget:** a call limit of 100,000 tokens, 80 calls and 1,200 seconds a trial, the same token budget a trial, and a dollar cap on every step. Genet's agents get 6 tool rounds; CrewAI's agents keep CrewAI's own 25 steps.
  - Why 100,000 and not the 64,000 first planned: at 64,000 a single filing is often larger than one call, and Genet's should-we gate refuses a split whose parts do not each fit a call (`PART_TOO_BIG`), so Genet would have refused nearly every split: every filing fits a part on 4 of 40 questions at 64,000, and on 39 of 40 at 100,000, while no whole question fits one call. 100,000 is also Haiku 5.5's price step: a longer prompt costs five times as much.
  - That gate rule predates paging, when a file had to fit a call to be read at all. It stays as it is for this test, and it is a finding: on real filings at a tighter limit, Genet's rule would keep it one agent.
- **The path to the model:** every CrewAI call goes through Genet's Anthropic adapter. So both sides are counted, capped, priced and recorded to a tape the same way, and both replay with no key.
- **No tuning on these questions.** Neither side's prompts change after the questions are drawn. CrewAI runs on its documented defaults except where the table below says otherwise.

| CrewAI setting | Value | Why |
|---|---|---|
| `llm`, `manager_llm` | CrewAI's own Anthropic provider, its client replaced by Genet's `RawClient` (`scripts/h2h_crewai.py`) | CrewAI builds every request itself, with native tool calls; every call is still sized, capped, counted, priced and taped by Genet. An empty slot would fall back to an OpenAI model. |
| context window | 100,000 (CrewAI uses 85% of it) | CrewAI's own default for a custom model is 4,096, which would summarise and move tool results to files |
| memory, knowledge, planning, cache | off | they embed or plan through OpenAI by default |
| `max_retry_limit` | 0 | a retry reruns the whole task outside the budget |
| `max_iter` | default (25) | CrewAI's own |
| telemetry | `CREWAI_DISABLE_TELEMETRY=true`, `OTEL_SDK_DISABLED=true`, `CREWAI_DISABLE_TRACKING=true`, `CREWAI_TRACING_ENABLED=false`, `share_crew=False` | it sends spans to telemetry.crewai.com by default |
| provider keys in the environment | none | the adapter reads `TASKORG_ANTHROPIC_KEY` only, so any call that bypasses it fails at once instead of spending |

**The one known unfairness, settled.** Genet's adapter sends text and gets text; CrewAI's tuned path is the API's native tool calling. The pinned source showed a cleaner way than a text adapter: CrewAI's own Anthropic provider builds its client in one method, so the harness keeps the provider and swaps only the client. CrewAI therefore runs its native tool calls, its message formats, its stop words and its own handling of a full context, and Genet's `RawClient` only sizes, caps, counts and records what goes out. Sampling settings CrewAI would add (`temperature`, `top_p`) are dropped, as Genet sends none, and both sides send effort low. Rehearsed on a stand-in API, CrewAI's requests replay from the tape exactly, 20 of 20.

Results are also shown against spend, since tokens drive much of any agent system's accuracy.

## What was built first (offline, $0)

The rehearsal turned up three things the generated notes never did, each fixed for both sides alike:
- **Sizes.** Genet measured a file as what one unpaged read returns, 4,000 characters, so its size note called 150,000-character filings "about 1,000 tokens". With paging on, a file now counts whole (`Toolbox._readable_chars`); unpaged runs measure as before.
- **File names.** A Loong comparison question names no company, so a lead could not name a file for a part, and neither could the told crew. Both benchmarks show the model each document's title (Loong heads each filing with its name; HotpotQA gives each paragraph's title), so each question's context now lists its files. Every contender, CrewAI included, gets the same context.
- **The token ratio.** The gates size files in the model's own tokens, 1.75 times four characters a token for Claude, so the rehearsal's stand-in reader uses that ratio too.

With those, the stand-in reader proposing one part a file: Genet stayed one agent on all 20 HotpotQA questions (every part refused, "fits in one context") and split on all 40 Loong questions (no part refused). One agent, the told crew and Genet finished every trial of both sets.

1. **A paged read.** Genet's `read` returns the first 4,000 characters of a file and cannot go further. That was sized for 900-token notes; a filing is tens of thousands of tokens.
   - `read:PATH@N` returns page N, with a line saying how many pages there are, and the page size is a setting. This test uses 16,000 characters, about 4,000 tokens, for both sides.
   - Off by default, so every tape recorded so far replays unchanged.
2. **Loaders.**
   - Loong: each question's documents become files in a workspace, named by company and filing, and the goal is the question and its instruction.
   - HotpotQA: each paragraph becomes a file named by its Wikipedia title.
3. **A judge,** run after the trials, on its own.
   - Loong's own prompt (Apache-2.0), which scores 1 to 100, run by Sonnet 5.5, not the model under test, and blind to which contender answered.
   - "Right" was to be Loong's perfect rate, a score of 100. The calibration showed the judge does not give 100 to answers that match, so right is a score of at least 80 in a finished run; Loong's average and the count at 100 are reported beside it.
   - The judge's calls are taped and capped like the rest, and 20 of its verdicts are read by hand before results are written.
4. **The CrewAI harness,** in its own virtual environment outside the project's: the adapter-backed `BaseLLM`, the tool wrappers and the settings above. It is checked against the pinned version's source, not the docs, since the research found places where the two differ.
5. **A rehearsal** of every contender on both sets against the simulated reader and the fake Messages endpoint, at $0, to check plumbing, tapes and the caps.
6. **Tests and mutation entries** for the paged read, the loaders and the judge, as for any kernel change.
7. **A live-session mode** with these bars in its header, a calibration gate and a firm estimate.

## Cost

A rough estimate before calibration, on Haiku 5.5 at $0.10 and $0.50 a million tokens. The filings are larger than first thought, and at a 100,000 limit an agent may carry up to about 100,000 tokens a call:

| Step | Trials | Rough cost | Cap |
|---|---|---|---|
| Calibration: 4 Loong questions, each contender, and the judge on them | 16 | about $1.20 | $2.30 |
| Loong: 40 questions, one agent, the told crew and Genet | 120 | about $4 to $7 | $8.00 |
| Loong: 40 questions, CrewAI | 40 | about $3 to $6; each step of an agent re-sends everything before it | $8.00 |
| HotpotQA control: 20 questions, 4 contenders | 80 | about $0.30 | $0.50 each side |
| Judge, Sonnet 5.5, Loong answers only | 160 | about $0.70 | $1.50 |
| All | | **about $10 to $16** | $20.80 |

The calibration stops the run if any contender stops on size, a malformed reply, the API or a crash on more than one of its 4 trials, or if the estimate it prints passes $15 or either side's Loong estimate passes 90% of its cap. The main run waits for a second y. About $99 of the month's credit is left.

## The calibration (9 November, $0.26)

Four Loong questions, one of each kind, under each contender, then the judge: $0.16 for one agent, the told crew and Genet, $0.05 for CrewAI, $0.05 for the judge. No contender stopped on size, a malformed reply, the API or a crash; one agent's grouping answer stopped at its checker. The gate's estimate for the main run was about $3, not $10 to $16: these questions ran on fewer tokens than the rough estimate allowed.

| Judge score | one agent | told crew | Genet | CrewAI |
|---|---|---|---|---|
| Spotlight (one figure) | 92 | 95 | 93 | 92 |
| Comparison | 97 | 95 | 92 | 92 |
| Clustering | 88, stopped at its checker | 80 | 2 | 92 |
| Chain | 2 | 30 | 35 | 22 |
| Average | 69.8 | 75.0 | 55.5 | 74.5 |

What it showed:
- **The judge does not give full marks to answers that match.** Sonnet 5.5 scored answers that matched the gold one 92 to 97, one of them word for word identical (97), each time docking points for detail it said it could not check, although Loong's prompt says a fully correct answer gets 100. Under Loong's rule all 16 answers were wrong, and every bar would have compared zeros. Right answers scored 80 to 97 and wrong ones 2 to 35, with nothing between, so right became a score of at least 80 in a finished run. This was fixed in `data/exp/h2h_read.py` before the main run had results; the judge's own `correct` field keeps the 100 rule, and the reader shows both.
- **Loong's chain question labels years by filing.** Its gold answer gives growth "from 2023 to 2024" using the two 10-Ks filed in 2023 and 2024, which report fiscal 2022 and 2023. All four contenders read the fiscal years, said 2024 was not covered, and scored 2 to 35; three of them gave the right figures under the right years. This is in the questions, not in any contender, and it may lower every contender's chain score alike.
- **Genet stayed one agent on 3 of 4,** its lead proposing no split; the gates refused nothing. On the clustering question it read 466,000 tokens alone, then said the line asked about is not in the filings. The others answered from the nearest line (a change in retained earnings or accumulated deficit) and scored 80 to 92.

## The bars, written before the run

On Loong's 40 questions, where right is a judge score of at least 80 in a finished run (first written as 100; changed after the calibration and before the main run had results, see below):

| Bar | Needed |
|---|---|
| Accuracy | Genet right on at least the best of one agent, CrewAI and the told crew, less 3 |
| Cost | Genet's tokens a question, and cost a right answer, at most CrewAI's |
| Wrong finishes | Genet's finished-and-wrong answers at most CrewAI's |

On HotpotQA's 20 questions:

| Bar | Needed |
|---|---|
| One agent is enough | Genet stays one agent on at least 18 of 20 |
| At its cost | Genet within 1 right of one agent, at most 1.3 times its tokens |

Reported with no bar:
- how many agents CrewAI's manager used a question;
- its format errors;
- each contender's split rate and accuracy by kind of question: on Loong, chain of reasoning against the rest; on HotpotQA, bridge against comparison;
- accuracy against spend.

If Genet misses the accuracy bar, the result says Genet's rule costs answers on real documents, and that goes in the README beside the rest.

## What this would not show

- One subset of one benchmark, at one call limit, on one model, with 40 questions, so differences of 3 or fewer are noise.
- One framework, configured by us, not by people who know it well. CrewAI's defaults may not be what an expert would choose for document QA.
- A judge from the same model family as both contenders, though not the same model.
- Genet's prompts were refined on generated notes, not on these documents, and CrewAI's on neither; whether that favours either side is not known.

## What was fetched and installed, on the operator's say-so (9 November)

All in `data/h2h/`, which git ignores, with SHA-256 sums in `data/h2h/SHA256SUMS`:
- Loong's questions, `loong.jsonl` (3,511,069 bytes, from GitHub at commit 6d2115b), and its documents, `doc.zip` (33,915,268 bytes, over https). The archive was checked for paths outside its folder and links before only `doc/financial` was extracted: 574 filings, 49.9 MB.
- HotpotQA's 20 questions, `hotpotqa/questions.jsonl` (116 KB kept of 43 rows fetched).
- CrewAI 1.15.30 in its own environment, `data/h2h/venv-crewai` (867 MB). 138 packages, every one pinned to a release from before 25 October, so at least two weeks old (30 newer ones were held back a release), and installed against their hashes (`data/h2h/crewai-locked.txt`).

## Still waiting on a say-so

1. The calibration: ran 9 November on the operator's y.
2. The main run: ran 9 November on their second y; results in LIVE_TESTS.md.
3. Publishing the tapes: kept local until checked. SEC filings are public records and Loong's repository is Apache-2.0. HotpotQA's paragraphs are CC BY-SA 4.0, so published excerpts need attribution and the same licence.
