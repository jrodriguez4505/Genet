#!/bin/bash
# Two small team measurements on Claude. One key entry, one confirmation, each run capped.
#
#   bash scripts/team_runs.sh            the three runs below
#   bash scripts/team_runs.sh followup   the two follow-ups to them (2 November, docs/LIVE_TESTS.md):
#     - the cards again, now that a lead on a tight cap is told how to name a group's files;
#     - the false note under shared-full, which opens the file the note cites. The independent view's brief
#       is the same with or without the note, so its 29 October tape already answers for it.
#   bash scripts/team_runs.sh independent   split runs under --verify-view independent. It stops the false note,
#     but it leaves out the sub-agents' reports: does it fail more right answers after a split?
#   bash scripts/team_runs.sh size   the same 8 trials, now that a lead whose files do not fit one call is told
#     what they come to: do more leads split?
#   bash scripts/team_runs.sh wide   single, crew and genet side by side at an 8,000-token cap: all four question
#     types over 10 companies, then aggregate and breadth over 20. Does genet match the best baseline for less, do
#     leads stay single where a split is pointless, and does it hold at the limit of 4 sub-agents?
#   bash scripts/team_runs.sh crew   the crew on the wide run's questions, told what genet's lead is told about size.
#     Without this, the wide run's crew lines compare the notes as well as the staffing. All 4 question types run at
#     10 companies because naming fewer changes which questions the seeded suite draws.
#   bash scripts/team_runs.sh fixes   genet on the wide run's questions, now that a guessed file name no longer sinks
#     a plan and a sub-agent's room no longer depends on its siblings: does it recover the answers it lost?
#   bash scripts/team_runs.sh second   genet on the 20-company questions, now that a sub-agent keeps room for a
#     sub-agent's reply and a plan with a part too big gets a second try: do the three runs that stopped get through?
#   bash scripts/team_runs.sh next   two benches. Told why its first plan was refused, does a lead write one that fits?
#     And told its sources are a sample, does the verifier stop failing right answers after a split, and does it still
#     catch an error in a file it was shown?
#   bash scripts/team_runs.sh merges   the real merges on the tapes, reviewed under today's rule and three others, and
#     the two new rules on the built products, whose errors sit in files shown or not. Which rule stops the verifier
#     failing right answers, and does it still catch wrong ones?
#   bash scripts/team_runs.sh heldout   the rule from the merges run, on questions it has never seen: 5 seeds no tape has
#     used, single, the told crew and genet, all with --verify-rule both. Then each new merge reviewed under today's rule
#     and both, and the built products on a new seed. Stops at the first run that stops; run it again to go on, and
#     what finished is kept. The bar, written before any of it ran:
#   (today's rule, as this was written: the source rule alone, which merge-bench now calls none.)
#     - Fewer false failures: of right answers, both fails at most half as many as today's rule, and the products only
#       today's rule fails are at least 3 times those only both fails. Today's rule must fail at least 10, or it cannot say.
#     - Errors still caught: of wrong answers, those only today's rule fails are no more than 1, or 5% if that is more.
#     Both must hold for the rule to become the default.
#
# 1. The report bench (team design part 8): 24 sub-agent parts of 20-company aggregate questions, 12 with
#    the plan wrong for them (their files are a look-alike's or an unrelated company's), each run with the
#    default sub-agent brief and with --report-up. Does a sub-agent hand the wrong part back, or guess?
#    Only the sub-agents' calls go to the model.
# 2. The cards (team design part 7): genet with and without the members table in the lead's plan brief,
#    on 10-company aggregate questions at a cap where the material does not fit one call. Does the lead
#    propose differently, with fewer parts refused or failed?
#   bash scripts/team_runs.sh refine   two benches on what the held-out run found.
#     Heading: every right figure in the suite's files sits on a line with no year, so a sentence saying such a line takes
#     its file's heading could not lose on them. On seed 111, files where the heading does not hold for every line: 6
#     questions, 18 wrong products, 12 right ones and 6 controls, each under the source rule alone and the default rule.
#     Rework: each rework on the held-out tapes asked again, with and without what the verifier said.
#     The bars, written before the run:
#     - Heading. It cannot say unless the source rule alone catches at least 9 of the 18 wrong products. The sentence holds
#       if the wrong products only the source rule alone fails are at most 1, and the right products only the default rule
#       fails are at most 1, and the default rule catches at least 5 of the 6 controls. If so, the lead and sub-agents may
#       be told it. If not, it is reworded and tested again on another seed.
#     - Rework. It cannot say unless at least 10 products were wrong before. The reason stays on if, of those, it brings
#       right at least twice as many as the plain brief and at least 3 more, if those only it brings right are at least 3
#       times those only the plain brief brings right, and if the right products it alone turns wrong are at most 1, or 5%.
#       If not, the reason goes back off.
#   bash scripts/team_runs.sh whole   whole runs with v0.11.0's changes on together: the verifier's reason in the rework
#     brief, rounds that fit, and the heading sentence told to the lead and sub-agents. 5 seeds no tape has used, 106 to
#     110: 24 questions at 10 companies under the told crew and genet, and 6 at 20 under those and single, whose size stops
#     now go on. 330 trials.
#     Measured against the held-out run of the same shape, on seeds 101 to 105. Its told crew and genet, 300 trials: 270
#     right; 9 size stops at 20 companies; 19 answers that decline, leave out or hedge a figure or name; none finished with
#     a wrong figure or name; 28,283 and 25,561 tokens a task. Its single at 20 companies: 0 of 30, each a size stop.
#     The bars, written before the run:
#     - Harm. The told crew and genet finish with a wrong figure or name at most 2 times in 300, and each spends at most 15%
#       more tokens a task. If either fails, the changes are tested apart before any move to Sonnet.
#     - Single at 20 companies. It finishes with a wrong figure or name at most 3 times in 30. A stop was an honest failure,
#       and going on must not hand back a wrong answer as complete. If it does, a cut round stops a single agent's run again.
#     - Rounds that fit. At 20 companies, size stops at most 2 of 60, and genet right on at least 24 of 30. If so, the
#       size problem counts as fixed. If not, it stays open.
#     - The heading sentence. Answers that decline, leave out or hedge a figure or name, at most 9 of 300. If so, and the
#       harm bar holds, --author-rule headed becomes the default. If not, it stays off.
#     - Right answers. At least 277 of 300, a quarter fewer wrong. Below 270 the changes are tested apart before Sonnet.
#     These are other questions than the reference's, so a few answers either way is noise, and with the changes on together
#     the run cannot say which did what. Reported with no bar: how many wrong products a rework puts right, against 7 of 22.
#   bash scripts/team_runs.sh rerun   the whole run again, now that a round leaves a lead 3,000 tokens to reply in. The run
#     above was stopped on 4 November after seed 106: at 20 companies all 14 of a lead's cut-off replies came right after a
#     cut round, so size stops had become stops on a malformed reply. Seeds 107 to 110 at 10 and 20 companies, and seed 112
#     at 20 in place of 106, which the fix was read from. Seed 106 at 10 companies counts as it ran: no round there was cut.
#     The bars are those above, unchanged but for one thing: in the rounds bar, a stop on a malformed reply counts as a size
#     stop, so the same failure cannot pass under another name. Reported with no bar: sub-agents' replies cut off.
#   bash scripts/team_runs.sh gaprule   the rerun's real merges, 224 of them, reviewed under both and under named, which adds
#     one sentence: a product that leaves out, sets aside or counts as zero anything the goal names has not answered it.
#     The rerun failed its harm bar, 6 finished wrong of 300; 5 of the 6 had set a named company aside and passed review.
#     The bars, written before the run:
#     - It cannot say unless both passes at least 4 of the wrong products here.
#     - Wrong answers. Named passes at most 1 of the wrong products, and fewer than both does.
#     - Right answers. Named fails at most 5 more of the right products than both does.
#     If both hold, named becomes the verifier's default. If not, it stays off and the harm stays an open problem.
#     Reported with no bar: the 6 that finished wrong, one by one, and right products that admit a gap.
#   bash scripts/team_runs.sh aside   the named sentence narrowed to what a product says of itself: a product that says
#     something the goal names has no figure, could not be found, counts as zero or was set aside has not answered it, and
#     keeping out look-alike names or other periods' figures is not that. The gap test failed named because it also failed
#     22 right products, most of which only listed some companies' figures or said look-alikes were kept out.
#     Two steps, one y:
#     1. The gap test's 224 merges under aside. The sentence was written from reading these, so this cannot decide; it only
#        saves the second step's spend. If aside passes more than 1 of the 37 wrong products, or fails more than 8 of the 187
#        right ones (both failed 3 there; 5 more), nothing more is run.
#     2. The deciding step: 318 merges whose products were not read for the sentence, from the held-out run (seeds 101 to
#        105) and the whole run (seeds 106 and 107), 274 right and 44 wrong. Each was recorded under both, and replays under
#        both with no misses, so both's verdict is the recorded one and only aside is paid for. The bars, written before
#        the run:
#        - It cannot say unless both passed at least 4 of the wrong products here. It passed 5.
#        - Wrong answers. Aside passes at most 1 of the 44 wrong products, and fewer than both did.
#        - Right answers. Aside fails at most 5 more of the 274 right products than both did.
#        If both hold, aside becomes the verifier's default. If not, it stays off and the harm stays an open problem.
#     The same kind of files with new figures, and a FAIL sends the work back for rework, so whether fewer runs finish wrong
#     is not measured here.
#   bash scripts/team_runs.sh gapcheck   a check in code, not a sentence for the model (--gap-check): a product the verifier
#     passed that says itself it has no figure for something, adds 0 for it or set it aside goes back once, with the
#     kernel's reason, and a product sent back for that which still says so stops the run. The narrower sentence (aside)
#     missed even on the merges it was written from. Each trial replays from its tape, and only a trial the check sends
#     back goes to the model from that point (--then-live). A free dry run of the rerun and held-out tapes, about 1,000
#     trials, found 19 such trials: 10 that finished wrong and 9 that finished right. Nothing else changes. Three rounds,
#     since one rework is one draw: 11 tapes each time. The bars, written before the run, on the mean of the three rounds:
#     - Wrong answers. Of the 10 that finished wrong, at most 3 still finish wrong.
#     - Right answers. Of the 9 that finished right, at most 2 no longer finish right.
#     If both hold, --gap-check becomes the default. If not, it stays off and the harm stays open.
#     The pattern was written from the rerun's merges, so 11 of the 19 trials are in sample for it; 8 are on the held-out
#     tapes. What a lead does with the reason was read from neither.
#   bash scripts/team_runs.sh sonnet   Claude Sonnet 5.5 on seed 108, the seed with the most of Haiku's finished-wrong
#     answers, with the rerun's settings, so each trial pairs with Haiku's on the same question. What is left of the harm on
#     Haiku is reading: a true figure next to a prior-year sentence or a look-alike's note, set aside. The gap check showed
#     that no rework put one right in 30 tries. Two steps, a y each:
#     1. Calibration: 4 trials at 20 companies (one aggregate and one breadth question, the told crew and Genet), about
#        $0.60 to $1.10, stopping itself before $1.50. The kernel's sizes and reply room were measured on Haiku. If any
#        trial stops on size, a malformed reply or the API (BUDGET, SCHEMA, LIVE), or takes over 450 of its 600 seconds,
#        nothing more runs. Otherwise it prints a firm estimate for step 2.
#     2. Seed 108: 24 questions at 10 companies under the told crew and Genet, and 6 at 20 under single, the told crew and
#        Genet: 66 trials, each size capped at $6.00. Haiku on the same trials (rerun-s108-10 and -20): right 22 and 23 at
#        10, 0, 5 and 2 at 20; finished wrong 4 (the told crew's compare-6 at 10; single's breadth-2 and Genet's aggregate-2
#        and aggregate-3 at 20); $0.47.
#     The bars, written before the run:
#     - Reading. Sonnet finishes wrong at most 1 time in 66, and is right on at least 3 of the 4 trials Haiku finished wrong.
#       If both hold, the harm counts as a limit of Haiku's reading, and the next test is a mixed team, Sonnet where the
#       reading is done. If not, the harm is not only the model's, and stays open as it is.
#     - Reported with no bar: right answers by strategy against Haiku's, tokens and cost a right answer, stops at 20.
#     One seed can show a large difference, not a small one.
#   bash scripts/team_runs.sh sonnettwo   the same on seed 110, with the rerun's settings, no calibration: it passed for these
#     settings on 7 November. On seed 108 Sonnet finished nothing wrong (Haiku 4), but was right on 2 of the 4 trials Haiku
#     finished wrong, where the bar asked 3: both misses were stops, one a verifier failing a right total. That bar stays
#     missed whatever this run shows. Haiku on seed 110 (rerun-s110-10 and -20): right 23 and 23 at 10, 1, 5 and 5 at 20;
#     finished wrong 2, the told crew's and Genet's breadth-6 at 10; $0.43. About $5.40, each size capped at $6.00.
#     The bars, written before the run:
#     - Sonnet finishes wrong at most 1 time in 66.
#     - Sonnet is right on both trials Haiku finished wrong.
#     If both hold, the next test is a mixed team, to find which role needs Sonnet: across two seeds it would have finished
#     nothing wrong. If either misses, Sonnet makes the same mistake, and a mixed team is not worth building for it.
#   bash scripts/team_runs.sh agents   how many agents a task needs: the same questions split by the kernel into 2, 4, 10 or
#     20 parts (split-N, one sub-agent a part, the lead merges), against one agent, the told crew and Genet. Questions over
#     all 20 companies (aggregate and breadth, 6 a seed) on seeds 113 and 114, which no tape has used, on Haiku 5.5. Twice:
#     at a call limit of 8,000 tokens, where the 20 files (about 17,500 tokens) do not fit one call, and at 64,000, where
#     they do. 168 trials, every strategy given 80 calls, about $2.20 and 2.5 hours; each of 4 steps stops itself before
#     $1.50. Twenty sub-agents call at once, so a rate limit can fail parts: those are counted on their own.
#     The bars, written before the run, each over the 12 questions of both seeds:
#     Where the work does not fit one call (8,000):
#     - Splitting is needed. The best split-N is right on at least 6 more questions than one agent.
#     - Past a handful, more agents do not pay. Split-20 is right on no more questions than the better of split-4 and
#       split-10, and spends at least 1.3 times its tokens a question. If split-20 matches it for no more tokens, the cap
#       of 4 sub-agents is too low.
#     - Genet's own plan is right on at most 1 question fewer than the best split-N, for at most 1.2 times its tokens. If
#       not, the lead's plan is the weak part, not the count.
#     Where it fits (64,000):
#     - One is enough. No split-N is right on more than 1 question more than one agent.
#     - Genet stays one agent on at least 10 of the 12.
#     Reported with no bar: whether a split costs fewer tokens than one agent even where the work fits (in the simulator
#     4 parts do, because one agent re-sends what it has read every round); if so, the should-we rule needs a cost term.
#     This is still a small model of large work: 20 files of about 900 tokens each.
#   bash scripts/team_runs.sh cache   prompt caching (TASKORG_MODEL_CACHE=1): a call that may go on to tool rounds is sent in
#     blocks cut where each round begins, so a round reads what came before it from the cache at a tenth of the price.
#     The agent-count sweep found that where the work fits one call (64,000), one agent spent twice what 4 parts did,
#     because it sends everything it has read again every round. Does caching close that? The sweep's 64,000 questions
#     again (seeds 113 and 114), one agent, 4 parts and Genet, cached: 36 trials on Haiku 5.5, about $0.25, each seed
#     stopping itself before $0.50. Uncached, a question cost: one agent $0.0129 (11 right of 12), 4 parts $0.0079 (12),
#     Genet $0.0140 (11), priced from the sweep's tapes.
#     The bars, written before the run:
#     - Answers hold. Each strategy is right within 1 of its uncached count.
#     - Caching pays. One agent's cost a question falls by at least 30%.
#     - The gap. Cached, one agent costs at most 1.25 times what 4 parts do a question, cached. If so, the should-we rule
#       needs no cost term while caching is on. If not, it does.
#     If the first two hold, caching becomes the default.
#   bash scripts/team_runs.sh mixed   a mixed team: Haiku's lead and sub-agents, Sonnet's verifier (TASKORG_MODEL_NAME_VERIFY),
#     on seeds 108 and 110 with the rerun's settings, the told crew and Genet: 120 trials, each paired with Haiku's and
#     Sonnet's own. By the tapes the verifier is 14 to 20% of the tokens, so this costs about $2.20, against $9.59 for
#     Sonnet alone and $0.75 for Haiku alone on the same trials. The other way round, Sonnet reading and Haiku checking,
#     would cost about $8.14, close to Sonnet alone, so it is not run.
#     The bars, written before the run:
#     - Wrong answers. It finishes wrong at most 1 time in 120 (Haiku alone 5, Sonnet alone 0).
#     - Right answers. At least 105 of 120 (Haiku alone 108, Sonnet alone 116): a stricter checker may stop a few more.
#     If both hold, the team to use is Haiku's authors with Sonnet checking, at about a quarter of Sonnet's cost. If the
#     wrong-answer bar misses, the authors' reading needs Sonnet, and Sonnet alone is the choice.
#   bash scripts/team_runs.sh opus   Claude Opus 5.5 on seed 108 with the rerun's settings, so each trial pairs with Haiku's and
#     Sonnet's own: three models on the same 66 trials. Two steps, a y each, as for Sonnet. A calibration of 4 trials at 20
#     companies, about $1.10, stopping itself before $2.50; a stop on size, a malformed reply or the API, or a trial over 450
#     of its 600 seconds, and nothing more runs. Then the 66 trials, at about twice Sonnet's $5.82 by the price, each size
#     capped at $8.00. On seed 108 Haiku was right on 52 and finished wrong 4 times; Sonnet right on 59, wrong 0.
#     The bars, written before the run:
#     - Opus finishes wrong at most 1 time in 66.
#     - Splitting holds. At 20 companies the told crew and Genet together are right on at least 9 of 12, and one agent on
#       at most 1 of 6 (Haiku 7 and 0, Sonnet 11 and 0).
#     - Reported with no bar: right answers against Haiku's and Sonnet's, cost a right answer, the verifier's stops.
#     If the first holds, the wrong answers are a limit of the smallest model, not of Genet's design.
#   bash scripts/team_runs.sh sonnetsweep   the agent-count sweep at a call limit of 8,000 on Sonnet 5.5: seeds 113 and 114,
#     one agent, 4, 10 and 20 parts and Genet, 60 trials, about $9.40, each seed capped at $6.00. Does "about four" hold
#     on a stronger reader?
#     The bars, written before the run, Haiku's at 8,000:
#     - Splitting is needed. The best split is right on at least 6 more of 12 than one agent.
#     - Past a handful, more agents do not pay. 20 parts right on no more than the better of 4 and 10, for at least 1.3
#       times its tokens a question.
#     - Genet's own plan is right on at most 1 fewer than the best split, for at most 1.2 times its tokens.
#     If the second holds on Sonnet as on Haiku, about four is not a limit of the smaller model.
#   bash scripts/team_runs.sh headtohead   Genet against CrewAI on public questions (docs/HEAD_TO_HEAD.md), on Haiku 5.5.
#     Loong's English SEC filings, 40 questions (10 of each kind) and 4 for calibration; HotpotQA, 20 questions. One agent,
#     the told crew, Genet, and CrewAI 1.15.30 (a manager and 4 readers), every call of every contender through Genet's
#     counting, caps and tapes. A call limit of 100,000 tokens, 80 calls and 1,200 seconds a trial, 6 tool rounds for
#     Genet's agents (CrewAI's own 25 steps an agent), pages of 16,000 characters. Loong is scored by Loong's own judge
#     prompt on Sonnet 5.5; HotpotQA by exact match. Two steps, a y each. The calibration, about $1.20, stops itself if a
#     contender stops on size, a malformed reply, the API or a crash on more than 1 of its 4, or if the estimate passes
#     $15. Then the rest, caps $8.00 for each side on Loong, $0.50 on HotpotQA, $1.50 for the judge.
#     The bars, written before the run. On Loong, right is a judge score of 100 in a run that finished:
#     - Accuracy. Genet right on at least the best of one agent, CrewAI and the told crew, less 3.
#     - Cost. Genet's tokens a question, and its cost a right answer, at most CrewAI's.
#     - Wrong finishes. Genet finishes wrong no more often than CrewAI.
#     On HotpotQA:
#     - One agent is enough. Genet stays one agent on at least 18 of 20.
#     - At its cost. Genet right on at least one agent's less 1, at most 1.3 times its tokens.
#     Reported with no bar: agents a question, CrewAI's answers with no ANSWER line, split rate and accuracy by kind,
#     accuracy against spend. If Genet misses the accuracy bar, Genet's rule costs answers on real documents.
#   bash scripts/team_runs.sh wording   the wording note on Loong (docs/LIVE_TESTS.md, 9 November), on Haiku 5.5, with the
#     head-to-head's limits and judge: the told crew and Genet with --author-rule wording, every writer told that a filing
#     may name a line differently and to use the line that measures the same thing, say which, and answer. Two steps, a
#     y each. Step 1: the 9 questions where a split's parts said the named line was not in their filing, about $0.35.
#     Step 2: all 40, about $1.25. One agent and CrewAI are not rerun.
#     The bars, written before the run. Right is a judge score of at least 80 in a run that finished.
#     - Step 1, the 9. The told crew and Genet together right on at least 9 of 18 (3 and 3 on 9 November), and together
#       finished wrong at most 4 times (3 and 1). If it misses, step 2 is not run.
#     - Step 2, accuracy. Genet right on at least 22 of 40 (20 on 9 November; one agent 22; CrewAI 25 less 3).
#     - Step 2, no harm elsewhere. On the other 31, the told crew and Genet each right on at least 16 (17 each).
#     - Step 2, wrong finishes. Genet at most 15 (CrewAI's; Genet had 12).
#     Reported with no bar: the told crew's total, parts that still say a named line is missing, the checker's stops, cost.
#     If the bars hold, the split losses were the wording, and the note goes into Genet's writers by default.
#   bash scripts/team_runs.sh samenote   the same-measure note on Loong questions no earlier run used, on Haiku 5.5, with the
#     head-to-head's limits and judge. 12 questions drawn before the run (benchmarks.loong_fresh, seed 1109): 6 comparison
#     and 6 clustering. The told crew and Genet, once with today's briefs and once with --author-rule same --verify-rule
#     same: writers use a line that is the same measure under another name and say which, and not a line that adds or
#     leaves out items; the checker does not fail the first and fails the second. One y, about $0.70.
#     The bars, written before the run. Right is a judge score of at least 80 in a run that finished.
#     - With the note, the told crew and Genet together right on at least 2 more of 24 than without.
#     - With the note, together finished wrong no more often than without.
#     Reported with no bar: each arm by team, the checker's stops, parts that say a named line is missing, tokens.
#     If both hold, the note goes to the 40 of the head-to-head, then to the default. 12 questions are few: a difference
#     of 2 of 24 can be noise, so a hold is a reason for the larger run, not a result.
#   bash scripts/team_runs.sh rereads   a rework that may read (--rework-reads), on Haiku 5.5 with the head-to-head's
#     limits and judge. After a merge the lead holds no tools, so when the checker failed a merged product for a figure
#     not read or not confirmed, the rework could only reword it. With the switch, the rework takes the single agent's
#     skill and may read. Each trial replays from its tape (the head-to-head's 40 of 9 November, and the 12 fresh
#     questions without the note) and goes to the model only at the rework, so the same first merges and the same
#     failed checks are compared. 20 trials do: the told crew 8 and Genet 5 of the 40, and 4 and 3 of the 12. Then the
#     judge on the 20. One y, about $0.25.
#     The bars, written before the run. Right is a judge score of at least 80 in a run that finished.
#     As taped, the 20 finished right 0 times and wrong 3 times; the checker stopped 17, 6 of them on a right answer.
#     - Right finishes, at least 4 of the 20.
#     - Wrong finishes rise by at most half the right finishes gained.
#     - Genet's 40 of 9 November, with its 5 reworked trials as they finish now: right on at least 22 (it was 20; CrewAI
#       25 less 3), and wrong at most 15 (12; CrewAI's 15). The head-to-head's accuracy bar then holds.
#     Reported with no bar: each team apart, the checks the reworks passed or failed, what the reworks read, tokens.
#     If all three hold, the switch goes to a full rerun of the 40 under both teams, then to the default.
#   bash scripts/team_runs.sh splitrule   when to split (--split-policy reads; compare's genet-reads), on Haiku 5.5 with
#     the head-to-head's limits and judge. Today the gates admit a split when the goal's files do not fit one call. With
#     paged reads, one agent reads a long file a page at a time and keeps what it found, so the rule counts a page of
#     each file: when that fits, there is no planning call and the lead works alone. When it does not, the lead plans
#     and the gates judge its parts as today. Unpaged work is measured as today.
#     On the 54 Loong questions no earlier run used (compare --which rest: everything the main, calibration and fresh
#     draws left), Genet as it is and Genet under the rule, then the judge on the 108. One y, about $1.70.
#     Before the run, free (data/exp/splitrule_dry.py): on every synthetic tape (366 trials, 209 of them split, reads not
#     paged) the rule does what Genet did, request for request. On the head-to-head's 40, its 4 calibration questions
#     and its 20 HotpotQA questions it does what one agent did, request for request: on the 40, right 22, wrong 15,
#     stopped 3, against Genet's 20, 12 and 8, at 75k tokens a question against 88k. By the second bar below, that
#     in-sample result misses. On all 54 new questions the rule keeps the lead alone.
#     The bars, written before the run. Right is a judge score of at least 80 in a run that finished.
#     - Under the rule, right on at least 2 more of the 54 than Genet as it is.
#     - Wrong finishes rise by at most half the right finishes gained.
#     - Fewer tokens a question than Genet as it is.
#     Reported with no bar: stops; each of Loong's four levels; the questions Genet as it is split and those it kept to
#     one agent.
#     If all three hold, the rule goes to the default, on the operator's go-ahead. 54 questions are still few: a
#     difference of 3 or 4 can be noise.
#     Ran 10 November, $1.31: right 24 to 28, wrong finishes 24 to 24, tokens a question 65,133 to 72,614. The third
#     bar missed, so the rule stays off by default (docs/LIVE_TESTS.md).
#   bash scripts/team_runs.sh keeppages   a rework that keeps its pages (--rework-keeps), on Haiku 5.5. When the verifier
#     fails a product, the rework brief today starts without what the product's call read, so one agent's rework reads
#     the same pages again: on the split rule's 54, two such trials took 343k and 703k tokens. With the switch on, the
#     rework brief carries what that call read, as far as one call has room with a page to spare.
#     Each trial replays from its tape and goes to the model only at its rework, on the Loong tapes' 36 trials whose
#     rework follows a product that read (data/exp/keeppages_dry.py; every other trial replays as it ran): the
#     head-to-head's 40 (single 10, genet 6), its calibration (single 2, genet 1), the 12 fresh (genet 3) and the 54
#     (genet 3, genet-reads 11). Then the judge on the 36. One y, about $0.35 as first planned.
#     On 11 November the fresh step stopped at its $0.11 cap after one trial, which cost $0.058: a rework that keeps its
#     pages went on reading, and each call carried them all. Its cap and those of the steps after it were raised, the
#     bars unchanged; the fresh step runs again whole. About $0.80 in all, $0.21 of it spent before the stop.
#     Before the run, free (data/exp/keeppages_share.py): as taped, the 36 took 6,116,108 tokens, 2,475,963 of them from
#     the rework on, and ended right 7, wrong 19, stopped 10. Their kept reworks' first calls would come to 1,298,551.
#     The bars, written before the run. Right is a judge score of at least 80 in a run that finished.
#     - Tokens: the 36 take at most 5,497,118, the rework's 2,475,963 cut by at least a quarter.
#     - Right on at least 7 of the 36, as many as taped.
#     - Wrong finishes rise by at most half the right finishes gained.
#     Reported with no bar: stops; each tape; the split rule's three bars on the 54 with kept pages in both arms; the
#     40's single and Genet with kept pages, beside CrewAI. The 54's two long reworks suggested the switch, so the 54 are
#     in-sample for it; the other 22 trials' reworks were not looked at before.
#     If all three hold, kept pages go to the default, on the operator's go-ahead.
# 3. The verifier against an argument (team design part 2): the verify bench's two arms under the default
#    layered pick. In one, the author's note argues for the planted figure; in the other, every source file
#    the kernel opens carries an instruction to pass a wrong product or fail a right one. 36 reviews.
#
# The key lives only in this process and the Python it starts: not in shell history, not on any command
# line, not in a log, a tape or a results file. For several runs in a sitting, scripts/live_session.sh takes the key
# once and hands it to each run you approve.
set -u
mode="${1:-all}"
case "$mode" in
  all|followup|independent|size|wide|crew|fixes|second|next|merges|heldout|refine|whole|rerun|gaprule|aside|gapcheck|sonnet|sonnettwo|agents|cache|mixed|opus|sonnetsweep|headtohead|wording|samenote|rereads|splitrule|keeppages) ;;
  *) echo "Usage: bash scripts/team_runs.sh [followup|independent|size|wide|crew|fixes|second|next|merges|heldout|refine|whole|rerun|gaprule|aside|gapcheck|sonnet|sonnettwo|agents|cache|mixed|opus|sonnetsweep|headtohead|wording|samenote|rereads|splitrule|keeppages]. Nothing was run."; exit 1 ;;
esac
cd "$(dirname "$0")/.." || exit 1
PY="${PYTHON:-.venv/bin/python}"
if ! "$PY" -c "import anthropic" 2>/dev/null; then
  echo "Needs the SDK in $PY: python3 -m venv .venv && .venv/bin/pip install -e '.[anthropic]'"
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_PROFILE ANTHROPIC_CUSTOM_HEADERS TASKORG_ANTHROPIC_BASE

# Estimates from the sim's token counts, scaled by what Claude's counts ran to on 28 and 29 October.
echo "Genet team runs on Claude. Prices per million tokens, input / output:"
if [ "$mode" = opus ]; then
  echo "  3) claude-opus-5-5     \$4 / \$20        calibration about \$1.10 (cap \$2.50); then seed 108, about \$11.60 (caps \$16.00)"
elif [ "$mode" = sonnetsweep ]; then
  echo "  2) claude-sonnet-5-5   \$2 / \$10        about \$9.40 in all, each seed capped at \$6.00"
elif [ "$mode" = headtohead ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   calibration about \$1.20; then about \$10 to \$16 with the judge on Sonnet (caps \$18.50)"
elif [ "$mode" = samenote ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.70 with the judge on Sonnet (caps \$1.10)"
elif [ "$mode" = rereads ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.25 with the judge on Sonnet (caps \$0.67)"
elif [ "$mode" = splitrule ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$1.70 with the judge on Sonnet (caps \$2.90)"
elif [ "$mode" = keeppages ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.60 more with the judge on Sonnet (caps \$1.51 in all)"
elif [ "$mode" = wording ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.35, then about \$1.25 with the judge on Sonnet (caps \$3.10)"
elif [ "$mode" = cache ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.25 in all, each seed capped at \$0.50"
elif [ "$mode" = mixed ]; then
  echo "  1) claude-haiku-5-5 with claude-sonnet-5-5 checking   about \$2.20 in all, each step capped (\$3.80 in all)"
elif [ "$mode" = agents ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$2.20 in all, each of 4 steps capped at \$1.50"
elif [ "$mode" = sonnettwo ]; then
  echo "  2) claude-sonnet-5-5   \$2 / \$10        seed 110, about \$5.40 (caps \$12.00)"
elif [ "$mode" = sonnet ]; then
  echo "  2) claude-sonnet-5-5   \$2 / \$10        calibration about \$0.60 to \$1.10 (cap \$1.50); then seed 108, about \$5 to \$10 (caps \$12.00)"
elif [ "$mode" = gapcheck ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.15 in all, each of 33 steps capped at \$0.03 (\$1.00 at most)"
elif [ "$mode" = aside ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.54 in all, each step capped (\$0.75 in all)"
elif [ "$mode" = gaprule ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.42, capped at \$0.50"
elif [ "$mode" = rerun ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$1.82 in all, each run capped (\$3.00 in all)"
elif [ "$mode" = whole ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$2.05 in all, each run capped (\$3.35 in all)"
elif [ "$mode" = refine ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.17 in all, each run capped (\$0.30 in all)"
elif [ "$mode" = heldout ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$2.50 in all, each run capped (\$4.10 in all, and the smoke test)"
elif [ "$mode" = merges ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.64 in all, each run capped (\$1.00 in all, and the smoke test)"
elif [ "$mode" = next ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.10 in all, each run capped (\$0.20 in all, and the smoke test)"
elif [ "$mode" = second ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.06, capped at \$0.10, and the smoke test"
elif [ "$mode" = fixes ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.17 in all, each run capped (\$0.32 in all, and the smoke test)"
elif [ "$mode" = crew ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.20 in all, each run capped (\$0.37 in all, and the smoke test)"
elif [ "$mode" = wide ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.50 in all, each run capped (\$0.75 in all, and the smoke test)"
elif [ "$mode" = independent ] || [ "$mode" = size ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.05, capped at \$0.10, and the smoke test"
elif [ "$mode" = followup ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.09 in all, each run capped (\$0.18 in all, and the smoke test)"
else
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.12 in all, each run capped (\$0.37 in all)"
fi
if [ -n "${GENET_LIVE_SESSION:-}" ] && [ -n "${TASKORG_ANTHROPIC_KEY:-}" ]; then
  # scripts/live_session.sh holds the key for a sitting. With no smoke test, nothing is spent before this run's y.
  session=1
  if [ "$mode" = sonnet ] || [ "$mode" = sonnettwo ] || [ "$mode" = sonnetsweep ]; then
    model=claude-sonnet-5-5; pin=2; pout=10
  elif [ "$mode" = opus ]; then
    model=claude-opus-5-5; pin=4; pout=20
  else
    model=claude-haiku-5-5; pin=0.10; pout=0.50
  fi
  echo "Using the key this window holds, on $model. No smoke test: nothing is spent before your y."
else
  session=""
  pick=""
  want=1; { [ "$mode" = sonnet ] || [ "$mode" = sonnettwo ] || [ "$mode" = sonnetsweep ]; } && want=2; [ "$mode" = opus ] && want=3
  while [ -z "$pick" ]; do
    read -r -p "Model, type $want: " pick
  done
  case "$mode:$pick" in
    sonnet:2|sonnettwo:2|sonnetsweep:2) model=claude-sonnet-5-5; pin=2; pout=10 ;;
    sonnet:*|sonnettwo:*|sonnetsweep:*) echo "This run is on Sonnet: type 2. Nothing was run."; exit 1 ;;
    opus:3) model=claude-opus-5-5; pin=4; pout=20 ;;
    opus:*) echo "This run is on Opus: type 3. Nothing was run."; exit 1 ;;
    *:1) model=claude-haiku-5-5; pin=0.10; pout=0.50 ;;
    *) echo "Only Haiku runs from this script, but for its sonnet run. Nothing was run."; exit 1 ;;
  esac
  read -r -s -p "Anthropic API key (typing is hidden; paste and press Enter): " key
  echo
  if [ -z "$key" ]; then
    echo "No key entered. Nothing was run."
    exit 1
  fi
  export TASKORG_ANTHROPIC_KEY="$key"
  unset key
  echo "Key received (${#TASKORG_ANTHROPIC_KEY} characters, not shown)."
fi
export TASKORG_MODEL_NAME="$model" TASKORG_MODEL_EFFORT=low

stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p data/compare data/tapes

if [ -z "$session" ]; then
echo
echo "== Smoke test: one lookup task, single agent (capped at \$0.05)"
"$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --per-family 1 --families lookup \
  --strategies single --context 200000 --max-spend 0.05 --out "data/compare/team-smoke-$stamp.json" >/dev/null 2>&1
"$PY" -I - "data/compare/team-smoke-$stamp.json" <<'EOF' || { echo "Smoke test did not pass. Nothing more was run."; exit 1; }
import json, sys
try:
    r = json.load(open(sys.argv[1]))["results"][0]
except (OSError, ValueError, KeyError, IndexError) as e:
    sys.exit(f"no smoke result: {e}")
print(f"smoke: {r['status']}, answer {r['answer']!r} (expected {r['expected']!r}), {r['calls']} calls")
if r["calls"] == 0 or r["code"] in ("LIVE", "CRASH") or not r["correct"]:
    sys.exit("the smoke test did not get the right answer")
EOF
fi

if [ "$mode" = heldout ] || [ "$mode" = refine ] || [ "$mode" = whole ] || [ "$mode" = rerun ] || [ "$mode" = gaprule ] || [ "$mode" = aside ] || [ "$mode" = gapcheck ] || [ "$mode" = sonnet ] || [ "$mode" = sonnettwo ] || [ "$mode" = agents ] || [ "$mode" = cache ] || [ "$mode" = mixed ] || [ "$mode" = opus ] || [ "$mode" = sonnetsweep ] || [ "$mode" = headtohead ] || [ "$mode" = wording ] || [ "$mode" = samenote ] || [ "$mode" = rereads ] || [ "$mode" = splitrule ] || [ "$mode" = keeppages ]; then
  # Names with no time in them: a run that is cut off finds what finished, and a run done once is not paid for twice.
  held() {  # name, cap, the subcommand, its words. Ends the script unless this run finished.
    local name=$1 cap=$2 sub=$3
    shift 3
    if [ -f "data/compare/$name.json" ]; then
      echo "== $name: already done"
    else
      # A tape is the record of what was spent, so one a cut-off run left is kept, under a name of its own.
      [ -f "data/tapes/$name.jsonl" ] && mv "data/tapes/$name.jsonl" "data/tapes/$name-cut-$stamp.jsonl"
      echo
      echo "== $name"
      "$PY" -m taskorg.cli "$sub" --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend "$cap" "$@" \
        --record "data/tapes/$name.jsonl" --out "data/compare/$name.json" 2>&1 \
        | tee "data/compare/$name.log" | grep --line-buffered -E "^\[|^\| |^- |^(Right|Wrong) |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
    fi
    echo
    if [ ! -f "data/compare/$name.json" ]; then
      echo "$name did not finish, so nothing more was run. What finished is kept. To go on: bash scripts/team_runs.sh $mode"
      exit 1
    fi
    if grep -q '"stopped_after"' "data/compare/$name.json"; then
      echo "$name stopped early, at its cap or by you, so nothing more was run. What finished is kept. To run it again, move its results out of data/compare."
      exit 1
    fi
  }
fi
if [ "$mode" = opus ]; then
  echo
  echo ">>> Claude Opus 5.5 on seed 108, with the rerun's settings, so each trial pairs with Haiku's and Sonnet's. Two steps."
  echo "    1. Calibration, 4 trials at 20 companies: about \$1.10, stopping itself before \$2.50. A stop on size, a malformed"
  echo "       reply or the API, or a trial near its time limit, and nothing more runs."
  echo "    2. Seed 108, 66 trials: a firm estimate is shown after step 1, and it waits for a second y."
  echo "    Written before it ran: Opus finishes wrong at most 1 time in 66 (Haiku 4, Sonnet 0), and at 20 companies splitting"
  echo "    holds. The full bars are at the top of this script."
  read -r -p "Run step 1 now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  shared="--context 8000 --tool-rounds 4 --author-rule headed"
  twenty="--families aggregate,breadth --entities 20 --distractors 6"
  held opus-calib 2.50 compare --seed 108 $twenty --per-family 1 --strategies always-told,genet $shared
  # As for Sonnet: stops on settings measured on Haiku end it here; otherwise a firm estimate at this model's prices.
  if ! "$PY" -I - "$pin" "$pout" <<'EOF'
import json, sys
pin, pout = float(sys.argv[1]), float(sys.argv[2])
rows = json.load(open("data/compare/opus-calib.json"))["results"]
cost = [(r["prompt_tokens"] * pin + r["completion_tokens"] * pout) / 1e6 for r in rows]
for r, c in zip(rows, cost):
    print(f"  {r['strategy']:<11} {r['task_id']:<12} {r['status']:<8} {r['code'] or '-':<7} {r['calls']:>2} calls "
          f"{r['tokens']:>7,} tokens ${c:.3f} {r['latency_s']:>5.0f}s right={r.get('answer_right')}")
bad = [r for r in rows if r["code"] in ("BUDGET", "SCHEMA", "LIVE") or r["latency_s"] > 450]
mean = sum(cost) / max(1, len(cost))
# Haiku's trial at 10 companies cost 0.373 of its trial at 20 on seed 108 (rerun-s108-10 and -20).
estimate = mean * 18 + mean * 0.373 * 48
print(f"step 1: ${sum(cost):.3f}; a trial at 20 companies ${mean:.3f}; step 2 about ${estimate:.2f} (caps $8.00 and $8.00)")
if bad:
    print("step 1 found stops on settings measured on Haiku, so step 2 was not run:", [(r["task_id"], r["code"]) for r in bad])
    sys.exit(3)
if estimate > 15:
    print("step 2 would likely pass its caps, so it was not run")
    sys.exit(4)
EOF
  then
    echo "Results: data/compare/opus-calib.json"
    exit 0
  fi
  read -r -p "Run step 2, seed 108 on Opus, at the estimate above? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Step 2 not run."; exit 0 ;;
  esac
  held opus-s108-10 8.00 compare --seed 108 --families lookup,aggregate,compare,breadth --per-family 6 --entities 10 \
    --distractors 6 --strategies always-told,genet $shared
  held opus-s108-20 8.00 compare --seed 108 $twenty --per-family 3 --strategies single,always-told,genet $shared
  echo
  echo "Done. Results: data/compare/opus-*.json   Tapes: data/tapes/opus-*.jsonl"
  exit 0
fi
if [ "$mode" = headtohead ]; then
  H=data/h2h
  CREW_PY="$H/venv-crewai/bin/python"
  for f in "$H/loong-questions/loong.jsonl" "$H/loong-docs/doc/financial" "$H/hotpotqa/questions.jsonl" "$CREW_PY"; do
    [ -e "$f" ] || { echo "Missing $f (docs/HEAD_TO_HEAD.md says how it was fetched). Nothing was run."; exit 1; }
  done
  if ! PYTHONPATH=. "$CREW_PY" -c "import crewai, taskorg.rawcall" 2>/dev/null; then
    echo "The CrewAI environment cannot import crewai and taskorg. Nothing was run."; exit 1
  fi
  echo
  echo ">>> Genet against CrewAI on public questions, on $model (docs/HEAD_TO_HEAD.md). Two steps."
  echo "    1. Calibration: 4 Loong questions under one agent, the told crew, Genet and CrewAI, and the judge on them:"
  echo "       about \$1.20. A contender that stops on size, a malformed reply, the API or a crash on more than 1 of 4,"
  echo "       or an estimate past \$15, and nothing more runs."
  echo "    2. Loong's 40 and HotpotQA's 20 under all four, then the judge: a firm estimate after step 1, and a second y."
  echo "    Written before it ran: Genet right on at least the best of the others less 3, at no more tokens a question"
  echo "    and cost a right answer than CrewAI. The full bars are at the top of this script."
  read -r -p "Run step 1 now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  limits="--context 100000 --max-calls 80 --max-seconds 1200 --page-chars 16000"
  loong="--questions $H/loong-questions/loong.jsonl --docs $H/loong-docs/doc/financial"
  hotpot="--questions $H/hotpotqa/questions.jsonl"
  # CrewAI's runs: the same checks as held(), through the CrewAI environment's Python and Genet's raw client.
  crew_held() {  # name, cap, the harness's words
    local name=$1 cap=$2
    shift 2
    if [ -f "data/compare/$name.json" ]; then
      echo "== $name: already done"
    else
      [ -f "data/tapes/$name.jsonl" ] && mv "data/tapes/$name.jsonl" "data/tapes/$name-cut-$stamp.jsonl"
      echo
      echo "== $name"
      PYTHONPATH=. "$CREW_PY" scripts/h2h_crewai.py --model "$model" --price-in "$pin" --price-out "$pout" --max-spend "$cap" \
        "$@" --record "data/tapes/$name.jsonl" --out "data/compare/$name.json" </dev/null 2>&1 \
        | tee "data/compare/$name.log" | grep --line-buffered -E "^\[|^\| |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
    fi
    echo
    if [ ! -f "data/compare/$name.json" ]; then
      echo "$name did not finish, so nothing more was run. What finished is kept. To go on: bash scripts/team_runs.sh $mode"
      exit 1
    fi
    if grep -q '"stopped_after"' "data/compare/$name.json"; then
      echo "$name stopped early, at its cap or by you, so nothing more was run. What finished is kept."
      exit 1
    fi
  }
  judge_held() {  # name, cap, results files
    local name=$1 cap=$2
    shift 2
    local files=()
    for f in "$@"; do files+=(--results "data/compare/$f.json"); done
    if [ -f "data/compare/$name.json" ]; then
      echo "== $name: already done"
    else
      [ -f "data/tapes/$name.jsonl" ] && mv "data/tapes/$name.jsonl" "data/tapes/$name-cut-$stamp.jsonl"
      echo
      echo "== $name (Sonnet 5.5, Loong's own judge prompt)"
      "$PY" -m taskorg.cli h2h-judge "${files[@]}" --questions "$H/loong-questions/loong.jsonl" --model claude-sonnet-5-5 \
        --price-in 2 --price-out 10 --max-spend "$cap" --record "data/tapes/$name.jsonl" --out "data/compare/$name.json" 2>&1 \
        | tee "data/compare/$name.log" | grep --line-buffered -E "^\| |^judge|^saved"
    fi
    [ -f "data/compare/$name.json" ] || { echo "$name did not finish, so nothing more was run."; exit 1; }
  }
  held h2h-calib-genet 1.00 compare --benchmark loong --which calibration $loong --strategies single,always-told,genet \
    $limits --tool-rounds 6
  crew_held h2h-calib-crewai 1.00 --benchmark loong --which calibration $loong --call-limit 100000 --max-calls 80 \
    --max-seconds 1200 --page-chars 16000
  judge_held h2h-calib-judged 0.30 h2h-calib-genet h2h-calib-crewai
  if ! "$PY" -I - "$pin" "$pout" <<'EOF'
import json, sys
from collections import defaultdict
pin, pout = float(sys.argv[1]), float(sys.argv[2])
rows = json.load(open("data/compare/h2h-calib-judged.json"))["results"]
by = defaultdict(list)
for r in rows:
    by[r["strategy"]].append(r)
    c = (r["prompt_tokens"] * pin + r["completion_tokens"] * pout) / 1e6
    print(f"  {r['strategy']:<11} {r['task_id']:<15} {r['status']:<8} {r['code'] or '-':<7} {r['calls']:>2} calls "
          f"{r['tokens']:>9,} tokens ${c:.3f} {r['latency_s']:>5.0f}s w={r['workers']} judge {r.get('judge_score')}")
bad = {s: [r["task_id"] for r in rs if r["code"] in ("BUDGET", "SCHEMA", "LIVE", "CRASH")] for s, rs in by.items()}
bad = {s: ids for s, ids in bad.items() if len(ids) > 1}
per_q = {s: sum((r["prompt_tokens"] * pin + r["completion_tokens"] * pout) / 1e6 for r in rs) / len(rs) for s, rs in by.items()}
genet_side = sum(v for s, v in per_q.items() if s != "crewai") * 40
crew_side = per_q.get("crewai", 0) * 40
# HotpotQA: about a tenth of a Loong trial, by its size; the judge: about $0.004 an answer on Sonnet.
estimate = genet_side + crew_side + (genet_side + crew_side) / 10 + 160 * 0.004
print(f"step 2 about ${estimate:.2f}: Loong ${genet_side:.2f} for one agent, the told crew and Genet (cap $8.00), "
      f"${crew_side:.2f} for CrewAI (cap $8.00); HotpotQA and the judge the rest")
if bad:
    print("step 1 found a contender that stopped on more than 1 of 4, so step 2 was not run:", bad)
    sys.exit(3)
if estimate > 15 or genet_side > 7.2 or crew_side > 7.2:
    print("step 2 would likely pass its caps, so it was not run")
    sys.exit(4)
EOF
  then
    echo "Results: data/compare/h2h-calib-*.json"
    exit 0
  fi
  read -r -p "Run step 2, Loong's 40 and HotpotQA's 20 under all four, then the judge, at the estimate above? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Step 2 not run."; exit 0 ;;
  esac
  held h2h-loong-genet 8.00 compare --benchmark loong --which main $loong --strategies single,always-told,genet \
    $limits --tool-rounds 6
  crew_held h2h-loong-crewai 8.00 --benchmark loong --which main $loong --call-limit 100000 --max-calls 80 \
    --max-seconds 1200 --page-chars 16000
  held h2h-hotpot-genet 0.50 compare --benchmark hotpot $hotpot --strategies single,always-told,genet $limits --tool-rounds 6
  crew_held h2h-hotpot-crewai 0.50 --benchmark hotpot $hotpot --call-limit 100000 --max-calls 80 --max-seconds 1200 \
    --page-chars 16000
  judge_held h2h-loong-judged 1.50 h2h-loong-genet h2h-loong-crewai
  echo
  echo "Done. Results: data/compare/h2h-*.json   Tapes: data/tapes/h2h-*.jsonl"
  exit 0
fi
if [ "$mode" = wording ]; then
  H=data/h2h
  for f in "$H/loong-questions/loong.jsonl" "$H/loong-docs/doc/financial" data/compare/h2h-loong-judged.json; do
    [ -e "$f" ] || { echo "Missing $f (docs/HEAD_TO_HEAD.md). Nothing was run."; exit 1; }
  done
  nine="loong-25d28410,loong-28b770d3,loong-612f5816,loong-62d35f36,loong-7b470b0f,loong-a79e07a2,loong-c0c4d8ea,loong-de58f2e7,loong-fead16dd"
  echo
  echo ">>> The wording note on Loong, on $model: the told crew and Genet, every writer told that a filing may name a line"
  echo "    differently and to use the line that measures the same thing (docs/LIVE_TESTS.md, 9 November). Two steps."
  echo "    1. The 9 questions where a split's parts said the named line is not in their filing: about \$0.35, the judge"
  echo "       with it, stopping itself before \$0.60 and \$0.10. Bar: together right on at least 9 of 18 (6 on 9 November)."
  echo "    2. All 40, after a second y: about \$1.25, caps \$2.00 and \$0.40. The full bars are at the top of this script."
  read -r -p "Run step 1 now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  limits="--context 100000 --max-calls 80 --max-seconds 1200 --page-chars 16000 --tool-rounds 6 --author-rule wording"
  loong="--benchmark loong --which main --questions $H/loong-questions/loong.jsonl --docs $H/loong-docs/doc/financial"
  judge_held() {  # name, cap, results files
    local name=$1 cap=$2
    shift 2
    local files=()
    for f in "$@"; do files+=(--results "data/compare/$f.json"); done
    if [ -f "data/compare/$name.json" ]; then
      echo "== $name: already done"
    else
      [ -f "data/tapes/$name.jsonl" ] && mv "data/tapes/$name.jsonl" "data/tapes/$name-cut-$stamp.jsonl"
      echo
      echo "== $name (Sonnet 5.5, Loong's own judge prompt)"
      "$PY" -m taskorg.cli h2h-judge "${files[@]}" --questions "$H/loong-questions/loong.jsonl" --model claude-sonnet-5-5 \
        --price-in 2 --price-out 10 --max-spend "$cap" --record "data/tapes/$name.jsonl" --out "data/compare/$name.json" 2>&1 \
        | tee "data/compare/$name.log" | grep --line-buffered -E "^\| |^judge|^saved"
    fi
    [ -f "data/compare/$name.json" ] || { echo "$name did not finish, so nothing more was run."; exit 1; }
  }
  held h2h-wording-nine 0.60 compare $loong --ids "$nine" --strategies always-told,genet $limits
  judge_held h2h-wording-nine-judged 0.10 h2h-wording-nine
  if ! "$PY" -I - "$pin" "$pout" "$nine" <<'EOF'
import json, sys
pin, pout, nine = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3].split(",")
new = json.load(open("data/compare/h2h-wording-nine-judged.json"))["results"]
old = [r for r in json.load(open("data/compare/h2h-loong-judged.json"))["results"]
       if r["task_id"] in nine and r["strategy"] in ("always-told", "genet")]
right = lambda r: (r.get("judge_score") or 0) >= 80 and r["status"] == "complete"
wrong = lambda r: r["status"] == "complete" and not right(r)
for label, rows in (("9 November", old), ("with the note", new)):
    print(f"  {label:<14}" + "   ".join(f"{s}: right {sum(right(r) for r in rows if r['strategy'] == s)}, "
                                        f"wrong {sum(wrong(r) for r in rows if r['strategy'] == s)}, "
                                        f"stopped {sum(r['status'] != 'complete' for r in rows if r['strategy'] == s)}"
                                        for s in ("always-told", "genet")))
spent = sum((r["prompt_tokens"] * pin + r["completion_tokens"] * pout) / 1e6 for r in new)
estimate = spent * 3.1 + 80 * 0.004  # on 9 November the 40 cost 3.1 times the 9 ($0.95 and $0.31)
print(f"step 1 spent ${spent:.2f} on the trials; step 2 about ${estimate:.2f} with the judge (caps $2.00 and $0.40)")
ok = sum(map(right, new)) >= 9 and sum(map(wrong, new)) <= 4
print(f"bar: together right on {sum(map(right, new))} of 18 (needs 9) and wrong {sum(map(wrong, new))} (at most 4) -> "
      + ("holds" if ok else "MISSES"))
if not ok:
    print("step 1 missed its bar, so step 2 was not run")
    sys.exit(3)
if estimate > 2.0:
    print("step 2 would likely pass its cap, so it was not run")
    sys.exit(4)
EOF
  then
    echo "Results: data/compare/h2h-wording-nine*.json"
    exit 0
  fi
  read -r -p "Run step 2, all 40 under the told crew and Genet, then the judge, at the estimate above? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Step 2 not run."; exit 0 ;;
  esac
  held h2h-wording-all 2.00 compare $loong --strategies always-told,genet $limits
  judge_held h2h-wording-all-judged 0.40 h2h-wording-all
  echo
  echo "Done. Results: data/compare/h2h-wording-*.json   Tapes: data/tapes/h2h-wording-*.jsonl   Read: data/exp/wording_read.py"
  exit 0
fi
if [ "$mode" = samenote ]; then
  H=data/h2h
  for f in "$H/loong-questions/loong.jsonl" "$H/loong-docs/doc/financial"; do
    [ -e "$f" ] || { echo "Missing $f (docs/HEAD_TO_HEAD.md). Nothing was run."; exit 1; }
  done
  echo
  echo ">>> The same-measure note on 12 Loong questions no earlier run used (6 comparison, 6 clustering), on $model."
  echo "    The told crew and Genet, once without the note and once with it: writers use a line that is the same measure"
  echo "    under another name and say which; the checker does not fail that, and fails a line that adds or leaves out items."
  echo "    48 trials and the judge: about \$0.70, each part stopping itself (caps \$0.40, \$0.40, \$0.15, \$0.15)."
  echo "    Written before it ran: with the note, together right on at least 2 more of 24, and finished wrong no more often."
  echo "    The full bars are at the top of this script."
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  limits="--context 100000 --max-calls 80 --max-seconds 1200 --page-chars 16000 --tool-rounds 6"
  loong="--benchmark loong --which fresh --questions $H/loong-questions/loong.jsonl --docs $H/loong-docs/doc/financial"
  judge_held() {  # name, cap, results files
    local name=$1 cap=$2
    shift 2
    local files=()
    for f in "$@"; do files+=(--results "data/compare/$f.json"); done
    if [ -f "data/compare/$name.json" ]; then
      echo "== $name: already done"
    else
      [ -f "data/tapes/$name.jsonl" ] && mv "data/tapes/$name.jsonl" "data/tapes/$name-cut-$stamp.jsonl"
      echo
      echo "== $name (Sonnet 5.5, Loong's own judge prompt)"
      "$PY" -m taskorg.cli h2h-judge "${files[@]}" --questions "$H/loong-questions/loong.jsonl" --model claude-sonnet-5-5 \
        --price-in 2 --price-out 10 --max-spend "$cap" --record "data/tapes/$name.jsonl" --out "data/compare/$name.json" 2>&1 \
        | tee "data/compare/$name.log" | grep --line-buffered -E "^\| |^judge|^saved"
    fi
    [ -f "data/compare/$name.json" ] || { echo "$name did not finish, so nothing more was run."; exit 1; }
  }
  held h2h-fresh-plain 0.40 compare $loong --strategies always-told,genet $limits
  held h2h-fresh-same 0.40 compare $loong --strategies always-told,genet $limits --author-rule same --verify-rule same
  judge_held h2h-fresh-plain-judged 0.15 h2h-fresh-plain
  judge_held h2h-fresh-same-judged 0.15 h2h-fresh-same
  echo
  echo "Done. Results: data/compare/h2h-fresh-*.json   Tapes: data/tapes/h2h-fresh-*.jsonl   Read: data/exp/same_read.py"
  exit 0
fi
if [ "$mode" = rereads ]; then
  H=data/h2h
  for f in "$H/loong-questions/loong.jsonl" "$H/loong-docs/doc/financial" data/tapes/h2h-loong-genet.jsonl \
           data/tapes/h2h-fresh-plain.jsonl data/compare/h2h-loong-judged.json data/compare/h2h-fresh-plain-judged.json; do
    [ -e "$f" ] || { echo "Missing $f (docs/HEAD_TO_HEAD.md). Nothing was run."; exit 1; }
  done
  echo
  echo ">>> A rework that may read, on $model: after a merge, the lead's rework may read what the checker named."
  echo "    Each trial replays from its tape and goes to the model only at the rework: the 20 split trials whose merge"
  echo "    the checker failed (the head-to-head's 40, and the 12 fresh questions). Then the judge on the 20."
  echo "    About \$0.25, each step stopping itself (caps \$0.20, \$0.15, \$0.12, \$0.10, and \$0.10 for the judge)."
  echo "    Written before it ran: right finishes on at least 4 of the 20 (none as taped), wrong finishes up by at most half"
  echo "    of that, and Genet's 40 then right on at least 22. The full bars are at the top of this script."
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  # The settings the tapes were recorded with, so every request before the rework is the tape's own.
  limits="--context 100000 --max-calls 80 --max-seconds 1200 --page-chars 16000 --tool-rounds 6 --rework-reads --then-live"
  loong="--benchmark loong --questions $H/loong-questions/loong.jsonl --docs $H/loong-docs/doc/financial"
  main=data/tapes/h2h-loong-genet.jsonl
  fresh=data/tapes/h2h-fresh-plain.jsonl
  held h2h-rereads-main-told 0.20 compare $loong --which main --strategies always-told --replay $main $limits --ids \
    loong-1fd30966,loong-25d28410,loong-28b770d3,loong-5a035018,loong-612f5816,loong-7b470b0f,loong-b7e24eef,loong-de58f2e7 </dev/null
  held h2h-rereads-main-genet 0.15 compare $loong --which main --strategies genet --replay $main $limits --ids \
    loong-25d28410,loong-28b770d3,loong-7b470b0f,loong-a79e07a2,loong-af88d682 </dev/null
  held h2h-rereads-fresh-told 0.12 compare $loong --which fresh --strategies always-told --replay $fresh $limits --ids \
    loong-0b4ccc46,loong-6e3692e8,loong-af2ba1aa,loong-c9506966 </dev/null
  held h2h-rereads-fresh-genet 0.10 compare $loong --which fresh --strategies genet --replay $fresh $limits --ids \
    loong-23f9a12d,loong-62c2c5db,loong-e2caca7c </dev/null
  name=h2h-rereads-judged
  if [ -f "data/compare/$name.json" ]; then
    echo "== $name: already done"
  else
    [ -f "data/tapes/$name.jsonl" ] && mv "data/tapes/$name.jsonl" "data/tapes/$name-cut-$stamp.jsonl"
    echo
    echo "== $name (Sonnet 5.5, Loong's own judge prompt)"
    "$PY" -m taskorg.cli h2h-judge --results data/compare/h2h-rereads-main-told.json --results data/compare/h2h-rereads-main-genet.json \
      --results data/compare/h2h-rereads-fresh-told.json --results data/compare/h2h-rereads-fresh-genet.json \
      --questions "$H/loong-questions/loong.jsonl" --model claude-sonnet-5-5 --price-in 2 --price-out 10 --max-spend 0.10 \
      --record "data/tapes/$name.jsonl" --out "data/compare/$name.json" 2>&1 \
      | tee "data/compare/$name.log" | grep --line-buffered -E "^\| |^judge|^saved"
  fi
  [ -f "data/compare/$name.json" ] || { echo "$name did not finish, so nothing more was run."; exit 1; }
  "$PY" -I - <<'EOF'
import json
right = lambda r: (r.get("judge_score") or 0) >= 80 and r["status"] == "complete"
wrong = lambda r: r["status"] == "complete" and not right(r)
new = json.load(open("data/compare/h2h-rereads-judged.json"))["results"]
# Each trial as taped, from the judged results of the run it replays.
taped = {"main": "h2h-loong-judged", "fresh": "h2h-fresh-plain-judged"}
old = []
for r in new:
    which = "main" if r["source"].endswith(("main-told.json", "main-genet.json")) else "fresh"
    rows = json.load(open(f"data/compare/{taped[which]}.json"))["results"]
    old += [o for o in rows if (o["strategy"], o["task_id"]) == (r["strategy"], r["task_id"])]
def line(rows):
    stopped = [r for r in rows if r["status"] != "complete"]
    return (f"right {sum(map(right, rows))}, wrong {sum(map(wrong, rows))}, stopped {len(stopped)}"
            f" ({sum((r.get('judge_score') or 0) >= 80 for r in stopped)} on a right answer)")
for label, rows in (("as taped", old), ("may read", new)):
    print(f"  {label:<9} {len(rows)} trials: {line(rows)}")
    for s in ("always-told", "genet"):
        print(f"    {s:<12} {line([r for r in rows if r['strategy'] == s])}")
gained = sum(map(right, new)) - sum(map(right, old))
a = sum(map(right, new)) >= 4
b = sum(map(wrong, new)) - sum(map(wrong, old)) <= gained / 2
mine = {r["task_id"]: r for r in new if r["strategy"] == "genet" and r["source"].endswith("main-genet.json")}
forty = [mine.get(r["task_id"], r) for r in json.load(open("data/compare/h2h-loong-judged.json"))["results"]
         if r["strategy"] == "genet"]
c = sum(map(right, forty)) >= 22 and sum(map(wrong, forty)) <= 15
print(f"bar: right finishes {sum(map(right, new))} of {len(new)} (at least 4) -> {'holds' if a else 'MISSES'}")
print(f"bar: wrong finishes {sum(map(wrong, old))} -> {sum(map(wrong, new))}, up by at most half of {gained} -> {'holds' if b else 'MISSES'}")
print(f"bar: Genet's 40 right {sum(map(right, forty))} (at least 22), wrong {sum(map(wrong, forty))} (at most 15) -> {'holds' if c else 'MISSES'}")
EOF
  echo
  echo "Done. Results: data/compare/h2h-rereads-*.json   Tapes, what went to the model: data/tapes/h2h-rereads-*.jsonl"
  exit 0
fi
if [ "$mode" = splitrule ]; then
  H=data/h2h
  for f in "$H/loong-questions/loong.jsonl" "$H/loong-docs/doc/financial"; do
    [ -e "$f" ] || { echo "Missing $f (docs/HEAD_TO_HEAD.md). Nothing was run."; exit 1; }
  done
  echo
  echo ">>> When to split, on $model: the 54 Loong questions no earlier run used, Genet as it is and Genet under the rule"
  echo "    (a split needs work one agent reading a page of each file could not hold; when it can, no planning call)."
  echo "    Then the judge on the 108. About \$1.70 and 45 minutes, each step stopping itself (caps \$1.50, \$0.90, and"
  echo "    \$0.50 for the judge)."
  echo "    Written before it ran: under the rule, right on at least 2 more of the 54, wrong finishes up by at most half"
  echo "    of that, and fewer tokens a question. On the head-to-head's 40 the rule gives one agent's trials: right +2, wrong"
  echo "    +3, so the second bar missed in-sample. The full bars are at the top of this script."
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  limits="--context 100000 --max-calls 80 --max-seconds 1200 --page-chars 16000 --tool-rounds 6"
  loong="--benchmark loong --questions $H/loong-questions/loong.jsonl --docs $H/loong-docs/doc/financial --which rest"
  held h2h-split-today 1.50 compare $loong --strategies genet $limits </dev/null
  held h2h-split-reads 0.90 compare $loong --strategies genet-reads $limits </dev/null
  name=h2h-split-judged
  if [ -f "data/compare/$name.json" ]; then
    echo "== $name: already done"
  else
    [ -f "data/tapes/$name.jsonl" ] && mv "data/tapes/$name.jsonl" "data/tapes/$name-cut-$stamp.jsonl"
    echo
    echo "== $name (Sonnet 5.5, Loong's own judge prompt)"
    "$PY" -m taskorg.cli h2h-judge --results data/compare/h2h-split-today.json --results data/compare/h2h-split-reads.json \
      --questions "$H/loong-questions/loong.jsonl" --model claude-sonnet-5-5 --price-in 2 --price-out 10 --max-spend 0.50 \
      --record "data/tapes/$name.jsonl" --out "data/compare/$name.json" 2>&1 \
      | tee "data/compare/$name.log" | grep --line-buffered -E "^\| |^judge|^saved"
  fi
  [ -f "data/compare/$name.json" ] || { echo "$name did not finish, so nothing more was run."; exit 1; }
  "$PY" -I - <<'EOF'
import json
right = lambda r: (r.get("judge_score") or 0) >= 80 and r["status"] == "complete"
wrong = lambda r: r["status"] == "complete" and not right(r)
rows = json.load(open("data/compare/h2h-split-judged.json"))["results"]
today = {r["task_id"]: r for r in rows if r["strategy"] == "genet"}
reads = {r["task_id"]: r for r in rows if r["strategy"] == "genet-reads"}
def line(rs):
    rs = list(rs)
    stopped = [r for r in rs if r["status"] != "complete"]
    tok = sum(r["tokens"] for r in rs) / max(1, len(rs))
    return (f"{len(rs)} trials: right {sum(map(right, rs))}, wrong {sum(map(wrong, rs))}, stopped {len(stopped)}"
            f" ({sum((r.get('judge_score') or 0) >= 80 for r in stopped)} on a right answer), {tok:,.0f} tokens a question,"
            f" split {sum((r['workers'] or 0) > 0 for r in rs)}")
print(f"  Genet as it is     {line(today.values())}")
print(f"  under the rule     {line(reads.values())}")
split = [t for t, r in today.items() if (r["workers"] or 0) > 0]
alone = [t for t in today if t not in split]
families = sorted({r["family"] for r in today.values()})
groups = [("where Genet split", split), ("where it kept one agent", alone)]
groups += [(f"level {f[len('loong-'):]}", [t for t, r in today.items() if r["family"] == f]) for f in families]
for label, ids in groups:
    print(f"  {label}:")
    print(f"    Genet as it is   {line(today[t] for t in ids)}")
    print(f"    under the rule   {line(reads[t] for t in ids if t in reads)}")
gained = sum(map(right, reads.values())) - sum(map(right, today.values()))
added = sum(map(wrong, reads.values())) - sum(map(wrong, today.values()))
tok_t = sum(r["tokens"] for r in today.values()) / max(1, len(today))
tok_r = sum(r["tokens"] for r in reads.values()) / max(1, len(reads))
a, b, c = gained >= 2, added <= gained / 2, tok_r < tok_t
print(f"bar: right {sum(map(right, today.values()))} -> {sum(map(right, reads.values()))}, at least 2 more -> {'holds' if a else 'MISSES'}")
print(f"bar: wrong {sum(map(wrong, today.values()))} -> {sum(map(wrong, reads.values()))}, up by at most half of {gained} -> {'holds' if b else 'MISSES'}")
print(f"bar: tokens a question {tok_t:,.0f} -> {tok_r:,.0f}, fewer -> {'holds' if c else 'MISSES'}")
EOF
  echo
  echo "Done. Results: data/compare/h2h-split-*.json   Tapes, what went to the model: data/tapes/h2h-split-*.jsonl"
  exit 0
fi
if [ "$mode" = keeppages ]; then
  H=data/h2h
  for f in "$H/loong-questions/loong.jsonl" "$H/loong-docs/doc/financial" data/tapes/h2h-loong-genet.jsonl \
           data/tapes/h2h-calib-genet.jsonl data/tapes/h2h-fresh-plain.jsonl data/tapes/h2h-split-today.jsonl \
           data/tapes/h2h-split-reads.jsonl data/compare/h2h-loong-judged.json data/compare/h2h-calib-judged.json \
           data/compare/h2h-fresh-plain-judged.json data/compare/h2h-split-judged.json; do
    [ -e "$f" ] || { echo "Missing $f (docs/HEAD_TO_HEAD.md). Nothing was run."; exit 1; }
  done
  echo
  echo ">>> A rework that keeps its pages, on $model: when the verifier fails a product, the rework brief carries what the"
  echo "    product's call read, so the rework reads again only what is missing. Each trial replays from its tape and goes"
  echo "    to the model only at its rework: the 36 Loong trials whose rework follows a product that read. Then the judge"
  echo "    on the 36. About \$0.80 in all, each step stopping itself (caps \$0.15, \$0.13, \$0.03, \$0.03, \$0.30, \$0.12,"
  echo "    \$0.50, and \$0.25 for the judge). Steps that finished are not run again; the fresh step, stopped at its first"
  echo "    cap, runs again whole."
  echo "    Written before it ran: the 36 take at most 5,497,118 tokens (6,116,108 as taped), right on at least 7 of them"
  echo "    (7 as taped), and wrong finishes up by at most half the right gained. The full bars are at the top of this script."
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  # The settings the tapes were recorded with, so every request before the rework is the tape's own.
  limits="--context 100000 --max-calls 80 --max-seconds 1200 --page-chars 16000 --tool-rounds 6 --rework-keeps --then-live"
  loong="--benchmark loong --questions $H/loong-questions/loong.jsonl --docs $H/loong-docs/doc/financial"
  held h2h-keeps-main-single 0.15 compare $loong --which main --strategies single --replay data/tapes/h2h-loong-genet.jsonl \
    $limits --ids loong-83cac46c,loong-7b279316,loong-612f5816,loong-41b01b58,loong-751c3613,loong-1192a01e,loong-d29b8b36,loong-5a035018,loong-12588c71,loong-053361f2 </dev/null
  held h2h-keeps-main-genet 0.13 compare $loong --which main --strategies genet --replay data/tapes/h2h-loong-genet.jsonl \
    $limits --ids loong-612f5816,loong-9fd8f0e0,loong-1192a01e,loong-5a035018,loong-12588c71,loong-053361f2 </dev/null
  held h2h-keeps-calib-single 0.03 compare $loong --which calibration --strategies single --replay data/tapes/h2h-calib-genet.jsonl \
    $limits --ids loong-f396c611,loong-8bc4a2b9 </dev/null
  held h2h-keeps-calib-genet 0.03 compare $loong --which calibration --strategies genet --replay data/tapes/h2h-calib-genet.jsonl \
    $limits --ids loong-f396c611 </dev/null
  held h2h-keeps-fresh-genet 0.30 compare $loong --which fresh --strategies genet --replay data/tapes/h2h-fresh-plain.jsonl \
    $limits --ids loong-c9506966,loong-af2ba1aa,loong-197ead69 </dev/null
  held h2h-keeps-rest-genet 0.12 compare $loong --which rest --strategies genet --replay data/tapes/h2h-split-today.jsonl \
    $limits --ids loong-96942bc4,loong-0b59de4d,loong-ed234f29 </dev/null
  held h2h-keeps-rest-reads 0.50 compare $loong --which rest --strategies genet-reads --replay data/tapes/h2h-split-reads.jsonl \
    $limits --ids loong-05a8ab3a,loong-44b5d8c0,loong-5b14133c,loong-8ee4e095,loong-926878f8,loong-a62d61a2,loong-70d2f3da,loong-7d75bfc7,loong-ed234f29,loong-80bea483,loong-c87acb6c </dev/null
  name=h2h-keeps-judged
  if [ -f "data/compare/$name.json" ]; then
    echo "== $name: already done"
  else
    [ -f "data/tapes/$name.jsonl" ] && mv "data/tapes/$name.jsonl" "data/tapes/$name-cut-$stamp.jsonl"
    echo
    echo "== $name (Sonnet 5.5, Loong's own judge prompt)"
    "$PY" -m taskorg.cli h2h-judge --results data/compare/h2h-keeps-main-single.json --results data/compare/h2h-keeps-main-genet.json \
      --results data/compare/h2h-keeps-calib-single.json --results data/compare/h2h-keeps-calib-genet.json \
      --results data/compare/h2h-keeps-fresh-genet.json --results data/compare/h2h-keeps-rest-genet.json \
      --results data/compare/h2h-keeps-rest-reads.json \
      --questions "$H/loong-questions/loong.jsonl" --model claude-sonnet-5-5 --price-in 2 --price-out 10 --max-spend 0.25 \
      --record "data/tapes/$name.jsonl" --out "data/compare/$name.json" 2>&1 \
      | tee "data/compare/$name.log" | grep --line-buffered -E "^\| |^judge|^saved"
  fi
  [ -f "data/compare/$name.json" ] || { echo "$name did not finish, so nothing more was run."; exit 1; }
  "$PY" -I - <<'EOF'
import json
right = lambda r: (r.get("judge_score") or 0) >= 80 and r["status"] == "complete"
wrong = lambda r: r["status"] == "complete" and not right(r)
load = lambda name: json.load(open(f"data/compare/{name}.json"))["results"]
# Each step, and the judged run it replays: the trials as taped.
TAPED = {"main-single": "h2h-loong-judged", "main-genet": "h2h-loong-judged", "calib-single": "h2h-calib-judged",
         "calib-genet": "h2h-calib-judged", "fresh-genet": "h2h-fresh-plain-judged", "rest-genet": "h2h-split-judged",
         "rest-reads": "h2h-split-judged"}
step = lambda r: next(k for k in TAPED if r["source"].endswith(f"h2h-keeps-{k}.json"))
new = load("h2h-keeps-judged")
was = {k: {(r["strategy"], r["task_id"]): r for r in load(f)} for k, f in TAPED.items()}
old = [was[step(r)][(r["strategy"], r["task_id"])] for r in new]
def line(rows):
    rows = list(rows)
    stopped = [r for r in rows if r["status"] != "complete"]
    return (f"{len(rows)} trials: right {sum(map(right, rows))}, wrong {sum(map(wrong, rows))}, stopped {len(stopped)}"
            f" ({sum((r.get('judge_score') or 0) >= 80 for r in stopped)} on a right answer), {sum(r['tokens'] for r in rows):,} tokens")
print(f"  as taped     {line(old)}")
print(f"  pages kept   {line(new)}")
for k in TAPED:
    mine = [r for r in new if step(r) == k]
    print(f"    {k:<12} as taped {line(was[k][(r['strategy'], r['task_id'])] for r in mine)}")
    print(f"    {'':<12} kept     {line(mine)}")
gained = sum(map(right, new)) - sum(map(right, old))
tok = sum(r["tokens"] for r in new)
a, b, c = tok <= 5_497_118, sum(map(right, new)) >= 7, sum(map(wrong, new)) - sum(map(wrong, old)) <= gained / 2
print(f"bar: tokens {sum(r['tokens'] for r in old):,} -> {tok:,}, at most 5,497,118 -> {'holds' if a else 'MISSES'}")
print(f"bar: right {sum(map(right, old))} -> {sum(map(right, new))}, at least 7 -> {'holds' if b else 'MISSES'}")
print(f"bar: wrong {sum(map(wrong, old))} -> {sum(map(wrong, new))}, up by at most half of {gained} -> {'holds' if c else 'MISSES'}")
# Reported with no bar: the runs these trials belong to, with kept pages where a rework kept them.
def kept(name, strategy, steps):
    swap = {r["task_id"]: r for r in new if step(r) in steps and r["strategy"] == strategy}
    return [swap.get(r["task_id"], r) for r in load(name) if r["strategy"] == strategy]
def per(rows):
    return f"right {sum(map(right, rows))}, wrong {sum(map(wrong, rows))}, {sum(r['tokens'] for r in rows) / len(rows):,.0f} tokens a question"
today, rule = kept("h2h-split-judged", "genet", ["rest-genet"]), kept("h2h-split-judged", "genet-reads", ["rest-reads"])
print(f"the 54, pages kept (in-sample): Genet as it is {per(today)}; under the split rule {per(rule)}")
g = sum(map(right, rule)) - sum(map(right, today))
print(f"  the split rule's bars: right +{g} (at least 2), wrong {sum(map(wrong, rule)) - sum(map(wrong, today)):+} (at most half of"
      f" {g}), tokens {'fewer' if sum(r['tokens'] for r in rule) < sum(r['tokens'] for r in today) else 'not fewer'}")
crew = [r for r in load("h2h-loong-judged") if r["strategy"] == "crewai"]
print(f"the 40, pages kept: single {per(kept('h2h-loong-judged', 'single', ['main-single']))}; "
      f"Genet {per(kept('h2h-loong-judged', 'genet', ['main-genet']))}; CrewAI {per(crew)}")
EOF
  echo
  echo "Done. Results: data/compare/h2h-keeps-*.json   Tapes, what went to the model: data/tapes/h2h-keeps-*.jsonl"
  exit 0
fi
if [ "$mode" = sonnetsweep ]; then
  echo
  echo ">>> The agent-count sweep on $model: seeds 113 and 114 at a call limit of 8,000, one agent, 4, 10 and 20 parts and"
  echo "    Genet. 60 trials, about \$9.40 and an hour; each seed stops itself before \$6.00."
  echo "    Written before it ran: Haiku's bars at 8,000. The full bars are at the top of this script."
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  for seed in 113 114; do
    held "sonnetsweep-s$seed-8000" 6.00 compare --seed "$seed" --families aggregate,breadth --per-family 3 --entities 20 \
      --distractors 6 --strategies single,split-4,split-10,split-20,genet --context 8000 --tool-rounds 4 --max-calls 80
  done
  echo
  echo "Done. Results: data/compare/sonnetsweep-*.json   Tapes: data/tapes/sonnetsweep-*.jsonl"
  exit 0
fi
if [ "$mode" = cache ]; then
  echo
  echo ">>> Prompt caching on the sweep's 64,000 questions: one agent, 4 parts and Genet, seeds 113 and 114, on $model."
  echo "    36 trials, about \$0.25 and 30 minutes; each seed stops itself before \$0.50."
  echo "    Written before it ran: answers within 1 of uncached; one agent's cost a question falls by at least 30%; cached,"
  echo "    one agent costs at most 1.25 times 4 parts. The full bars are at the top of this script."
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  export TASKORG_MODEL_CACHE=1
  for seed in 113 114; do
    held "cache-s$seed-64000" 0.50 compare --seed "$seed" --families aggregate,breadth --per-family 3 --entities 20 \
      --distractors 6 --strategies single,split-4,genet --context 64000 --tool-rounds 4 --max-calls 80
  done
  echo
  echo "Done. Results: data/compare/cache-*.json   Tapes: data/tapes/cache-*.jsonl"
  exit 0
fi
if [ "$mode" = mixed ]; then
  echo
  echo ">>> A mixed team: Haiku's lead and sub-agents, Sonnet's verifier, on seeds 108 and 110 with the rerun's settings."
  echo "    The told crew and Genet, 120 trials, about \$2.20 and an hour; each step stops itself at its cap (\$3.80 in all)."
  echo "    Written before it ran: it finishes wrong at most 1 time in 120 (Haiku alone 5), and is right on at least 105"
  echo "    (Haiku alone 108). The full bars are at the top of this script."
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  export TASKORG_MODEL_NAME_VERIFY=claude-sonnet-5-5
  shared="--context 8000 --tool-rounds 4 --author-rule headed --price claude-sonnet-5-5=2/10"
  for seed in 108 110; do
    held "mixed-s$seed-10" 1.20 compare --seed "$seed" --families lookup,aggregate,compare,breadth --per-family 6 \
      --entities 10 --distractors 6 --strategies always-told,genet $shared
    held "mixed-s$seed-20" 0.70 compare --seed "$seed" --families aggregate,breadth --per-family 3 --entities 20 \
      --distractors 6 --strategies always-told,genet $shared
  done
  echo
  echo "Done. Results: data/compare/mixed-*.json   Tapes: data/tapes/mixed-*.jsonl"
  exit 0
fi
if [ "$mode" = agents ]; then
  echo
  echo ">>> How many agents a task needs: the same 20-company questions split by the kernel into 2, 4, 10 or 20 parts,"
  echo "    against one agent, the told crew and Genet, on $model. Seeds 113 and 114, at call limits of 8,000 (the files do"
  echo "    not fit one call) and 64,000 (they do). 168 trials, about \$2.20 and 2.5 hours; each of 4 steps stops itself"
  echo "    before \$1.50. The bars are at the top of this script."
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  for seed in 113 114; do
    for cap in 8000 64000; do
      held "agents-s$seed-$cap" 1.50 compare --seed "$seed" --families aggregate,breadth --per-family 3 --entities 20 \
        --distractors 6 --strategies single,split-2,split-4,split-10,split-20,always-told,genet --context "$cap" \
        --tool-rounds 4 --max-calls 80
    done
  done
  echo
  echo "Done. Results: data/compare/agents-*.json   Tapes: data/tapes/agents-*.jsonl"
  exit 0
fi
if [ "$mode" = sonnettwo ]; then
  echo
  echo ">>> Claude Sonnet 5.5 on seed 110, with the rerun's settings, so each trial pairs with Haiku's. 66 trials, about"
  echo "    \$5.40 and 30 minutes; each size stops itself before \$6.00."
  echo "    Written before it ran: Sonnet finishes wrong at most 1 time in 66 (Haiku 2), and is right on both trials Haiku"
  echo "    finished wrong. If so, the next test is a mixed team. The full bars are at the top of this script."
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  shared="--context 8000 --tool-rounds 4 --author-rule headed"
  held sonnet-s110-10 6.00 compare --seed 110 --families lookup,aggregate,compare,breadth --per-family 6 --entities 10 \
    --distractors 6 --strategies always-told,genet $shared
  held sonnet-s110-20 6.00 compare --seed 110 --families aggregate,breadth --entities 20 --distractors 6 --per-family 3 \
    --strategies single,always-told,genet $shared
  echo
  echo "Done. Results: data/compare/sonnet-s110-*.json   Tapes: data/tapes/sonnet-s110-*.jsonl"
  exit 0
fi
if [ "$mode" = sonnet ]; then
  echo
  echo ">>> Claude Sonnet 5.5 on seed 108, with the rerun's settings, so each trial pairs with Haiku's. Two steps, a y each."
  echo "    1. Calibration, 4 trials at 20 companies: about \$0.60 to \$1.10, stopping itself before \$1.50. A stop on size,"
  echo "       a malformed reply or the API, or a trial near its time limit, and nothing more runs."
  echo "    2. Seed 108, 66 trials: a firm estimate is shown after step 1, and it waits for a second y."
  echo "    Written before it ran: Sonnet finishes wrong at most 1 time in 66 (Haiku 4), and is right on at least 3 of the 4"
  echo "    trials Haiku finished wrong. The full bars are at the top of this script."
  read -r -p "Run step 1 now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  shared="--context 8000 --tool-rounds 4 --author-rule headed"
  twenty="--families aggregate,breadth --entities 20 --distractors 6"
  held sonnet-calib 1.50 compare --seed 108 $twenty --per-family 1 --strategies always-told,genet $shared
  # Stops on our settings, not the model's answers, end it here; otherwise a firm estimate from what Sonnet spent.
  if ! "$PY" -I - <<'EOF'
import json, sys
rows = json.load(open("data/compare/sonnet-calib.json"))["results"]
cost = [(r["prompt_tokens"] * 2 + r["completion_tokens"] * 10) / 1e6 for r in rows]
for r, c in zip(rows, cost):
    print(f"  {r['strategy']:<11} {r['task_id']:<12} {r['status']:<8} {r['code'] or '-':<7} {r['calls']:>2} calls "
          f"{r['tokens']:>7,} tokens ${c:.3f} {r['latency_s']:>5.0f}s right={r.get('answer_right')}")
bad = [r for r in rows if r["code"] in ("BUDGET", "SCHEMA", "LIVE") or r["latency_s"] > 450]
mean = sum(cost) / max(1, len(cost))
# Haiku's trial at 10 companies cost 0.373 of its trial at 20 on seed 108 (rerun-s108-10 and -20).
estimate = mean * 18 + mean * 0.373 * 48
print(f"step 1: ${sum(cost):.3f}; a trial at 20 companies ${mean:.3f}; step 2 about ${estimate:.2f} (caps $6.00 and $6.00)")
if bad:
    print("step 1 found stops on settings measured on Haiku, so step 2 was not run:", [(r["task_id"], r["code"]) for r in bad])
    sys.exit(3)
if estimate > 11:
    print("step 2 would likely pass its caps, so it was not run")
    sys.exit(4)
EOF
  then
    echo "Results: data/compare/sonnet-calib.json"
    exit 0
  fi
  read -r -p "Run step 2, seed 108 on Sonnet, at the estimate above? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Step 2 not run."; exit 0 ;;
  esac
  held sonnet-s108-10 6.00 compare --seed 108 --families lookup,aggregate,compare,breadth --per-family 6 --entities 10 \
    --distractors 6 --strategies always-told,genet $shared
  held sonnet-s108-20 6.00 compare --seed 108 $twenty --per-family 3 --strategies single,always-told,genet $shared
  echo
  echo "Done. Results: data/compare/sonnet-*.json   Tapes: data/tapes/sonnet-*.jsonl"
  exit 0
fi
if [ "$mode" = gapcheck ]; then
  echo
  echo ">>> A check in code: a product the verifier passed that says it has no figure for something, adds 0 for it or set"
  echo "    it aside goes back once with the kernel's reason. Each trial replays from its tape; only the 19 the check sends"
  echo "    back go to $model, three times each. About \$0.15 and 15 minutes; each of 33 steps stops itself before \$0.03."
  echo "    Written before it ran, on the mean of three rounds: of the 10 that finished wrong, at most 3 still do; of the 9"
  echo "    that finished right, at most 2 no longer do. If so, it becomes the default. The full bars are at the top."
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  # Each tape with its recorded settings, so every request before the check is the tape's own.
  shared="--context 8000 --tool-rounds 4 --max-calls 40 --verify-view independent --verify-sources layered --verify-rule both"
  ten="--families lookup,aggregate,compare,breadth --per-family 6 --entities 10 --distractors 6"
  twenty="--families aggregate,breadth --per-family 3 --entities 20 --distractors 6 --strategies single,always-told,genet"
  for round in 1 2 3; do
    while IFS='|' read -r tape words; do
      held "gapcheck-r$round-$tape" 0.03 compare $words $shared --gap-check --then-live \
        --replay "data/tapes/$tape.jsonl" </dev/null
    done <<EOF
rerun-s108-10|--seed 108 $ten --strategies always-told,genet --author-rule headed
rerun-s108-20|--seed 108 $twenty --author-rule headed
rerun-s109-10|--seed 109 $ten --strategies always-told,genet --author-rule headed
rerun-s109-20|--seed 109 $twenty --author-rule headed
rerun-s110-10|--seed 110 $ten --strategies always-told,genet --author-rule headed
rerun-s112-20|--seed 112 $twenty --author-rule headed
heldout-s101-10|--seed 101 $ten --strategies single,always-told,genet --no-rework-reason
heldout-s102-10|--seed 102 $ten --strategies single,always-told,genet --no-rework-reason
heldout-s103-10|--seed 103 $ten --strategies single,always-told,genet --no-rework-reason
heldout-s103-20|--seed 103 $twenty --no-rework-reason
heldout-s105-10|--seed 105 $ten --strategies single,always-told,genet --no-rework-reason
EOF
  done
  echo
  echo "Done. Results: data/compare/gapcheck-r*.json   Tapes, what went to the model: data/tapes/gapcheck-r*.jsonl"
  exit 0
fi
if [ "$mode" = aside ]; then
  echo
  echo ">>> The named sentence narrowed: a product that says something the goal names has no figure, could not be found,"
  echo "    counts as zero or was set aside has not answered it. On $model, about 15 minutes, about \$0.54 in two steps."
  echo "    1. The gap test's 224 merges, about \$0.22, stops itself before \$0.30. The sentence was written from these, so"
  echo "       this only checks it is worth the second step: past 1 wrong passed or 8 right failed, nothing more is run."
  echo "    2. 318 merges not read for it, about \$0.32, stops itself before \$0.45. Written before it ran: aside passes at"
  echo "       most 1 wrong product and fewer than both, and fails at most 5 more right ones than both. If so, it becomes the"
  echo "       verifier's default. The full bars are at the top of this script."
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  tapes=""
  for name in s107-10 s107-20 s108-10 s108-20 s109-10 s109-20 s110-10 s110-20 s112-20; do
    tapes="$tapes${tapes:+,}data/tapes/rerun-$name.jsonl"
  done
  held aside-insample 0.30 merge-bench --workers 4 --rules aside --tapes "$tapes"
  # The first step against the gap test's own both: past its limits, the second is not worth paying for.
  if ! "$PY" -I - <<'EOF'
import json, sys
def counts(path, rule):
    rows = [r for r in json.load(open(path))["results"] if r["rule"] == rule]
    return (sum(1 for r in rows if not r["right"] and r["verdict"] == "PASS"),
            sum(1 for r in rows if r["right"] and r["verdict"] == "FAIL"))
wrong_passed, right_failed = counts("data/compare/aside-insample.json", "aside")
_, both_failed = counts("data/compare/gaprule-merges.json", "both")
print(f"step 1: aside passed {wrong_passed} wrong (limit 1), failed {right_failed} right (both {both_failed}, limit {both_failed + 5})")
sys.exit(0 if wrong_passed <= 1 and right_failed <= both_failed + 5 else 3)
EOF
  then
    echo "Step 1 missed its limits, so step 2 was not run. Results: data/compare/aside-insample.json"
    exit 0
  fi
  tapes=""
  for name in heldout-s101-10 heldout-s101-20 heldout-s102-10 heldout-s102-20 heldout-s103-10 heldout-s103-20 \
              heldout-s104-10 heldout-s104-20 heldout-s105-10 heldout-s105-20 whole-s106-10 whole-s106-20 whole-s107-10; do
    tapes="$tapes${tapes:+,}data/tapes/$name.jsonl"
  done
  held aside-heldout 0.45 merge-bench --workers 4 --rules aside --tapes "$tapes"
  echo
  echo "Done. Results: data/compare/aside-insample.json and aside-heldout.json   Tapes: data/tapes/aside-*.jsonl"
  exit 0
fi
if [ "$mode" = gaprule ]; then
  echo
  echo ">>> The rerun's 224 real merges, each reviewed under both and under named, on $model, about 10 minutes."
  echo "    Named adds one sentence: a product that leaves out, sets aside or counts as zero anything the goal names"
  echo "    has not answered it. About \$0.42; it stops itself before \$0.50."
  echo "    Written before it ran: named passes at most 1 wrong product and fewer than both, and fails at most 5 more"
  echo "    right products than both. If so, it becomes the verifier's default. The full bars are at the top of this script."
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  tapes=""
  for name in s107-10 s107-20 s108-10 s108-20 s109-10 s109-20 s110-10 s110-20 s112-20; do
    tapes="$tapes${tapes:+,}data/tapes/rerun-$name.jsonl"
  done
  held gaprule-merges 0.50 merge-bench --workers 4 --rules both,named --tapes "$tapes"
  echo
  echo "Done. Results: data/compare/gaprule-merges.json   Tape: data/tapes/gaprule-merges.jsonl"
  exit 0
fi
if [ "$mode" = rerun ]; then
  echo
  echo ">>> Whole runs again, now that a round leaves a lead 3,000 tokens to reply in, on $model, about 3 hours."
  echo "    Run it again to go on if it is cut off. Keep the lid open: a sleeping Mac stalls it."
  echo "    Seeds 107 to 110: 24 questions at 10 companies, the told crew and genet, about \$0.23; it stops itself before \$0.35."
  echo "    Seeds 107 to 110 and 112: 6 at 20 companies, the told crew, genet and single, about \$0.18; it stops itself before \$0.32."
  echo "    On in every run: the verifier's reason in the rework brief, rounds that fit and the heading sentence for authors."
  echo "    Written before it ran, against the held-out run on other questions, told crew and genet, 300 trials,"
  echo "    with seed 106 at 10 companies counted as it ran:"
  echo "      at most 2 finish with a wrong figure or name (it had 0), at most 15% more tokens a task;"
  echo "      size stops and stops on a malformed reply at 20 companies at most 2 of 60 (it had 9),"
  echo "      and genet right on at least 24 of 30 there (it had 22);"
  echo "      answers that decline or leave out a figure at most 9 (it had 19); at least 277 right (it had 270)."
  echo "      Single at 20 companies finishes with a wrong figure or name at most 3 of 30."
  echo "    The full bars are at the top of this script."
  read -r -p "Run them now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  # Hours long: keep the machine from idling to sleep for as long as this script runs, and no longer.
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  for seed in 107 108 109 110 112; do
    if [ "$seed" != 112 ]; then
      held "rerun-s$seed-10" 0.35 compare --seed "$seed" --per-family 6 --entities 10 --distractors 6 \
        --strategies always-told,genet --context 8000 --tool-rounds 4 --author-rule headed
    fi
    held "rerun-s$seed-20" 0.32 compare --seed "$seed" --families aggregate,breadth --per-family 3 --entities 20 --distractors 6 \
      --strategies single,always-told,genet --context 8000 --tool-rounds 4 --author-rule headed
  done
  echo
  echo "Done. Results: data/compare/rerun-*.json   Tapes: data/tapes/rerun-*.jsonl"
  exit 0
fi
if [ "$mode" = whole ]; then
  echo
  echo ">>> Whole runs with the changes on together, on $model, about 2 hours. Run it again to go on if it is cut off:"
  echo "    5 seeds no tape has used (106 to 110), each: 24 questions at 10 companies, the told crew and genet, about \$0.23;"
  echo "      it stops itself before \$0.35. And 6 at 20 companies, the told crew, genet and single, about \$0.18, of which"
  echo "      single's 6 trials are about \$0.06 and at most about \$0.13; it stops itself before \$0.32."
  echo "    On in every run: the verifier's reason in the rework brief, rounds that fit, and the heading sentence for authors."
  echo "    Written before it ran, against the held-out run on other questions, told crew and genet, 300 trials:"
  echo "      at most 2 finish with a wrong figure or name (it had 0), at most 15% more tokens a task;"
  echo "      size stops at 20 companies at most 2 of 60 (it had 9), and genet right on at least 24 of 30 there (it had 22);"
  echo "      answers that decline or leave out a figure at most 9 (it had 19); at least 277 right (it had 270)."
  echo "      Single at 20 companies finishes with a wrong figure or name at most 3 of 30."
  echo "    The full bars are at the top of this script."
  read -r -p "Run them now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  # Hours long: keep the machine from idling to sleep for as long as this script runs, and no longer.
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  for seed in 106 107 108 109 110; do
    held "whole-s$seed-10" 0.35 compare --seed "$seed" --per-family 6 --entities 10 --distractors 6 \
      --strategies always-told,genet --context 8000 --tool-rounds 4 --author-rule headed
    held "whole-s$seed-20" 0.32 compare --seed "$seed" --families aggregate,breadth --per-family 3 --entities 20 --distractors 6 \
      --strategies single,always-told,genet --context 8000 --tool-rounds 4 --author-rule headed
  done
  echo
  echo "Done. Results: data/compare/whole-*.json   Tapes: data/tapes/whole-*.jsonl"
  exit 0
fi
if [ "$mode" = refine ]; then
  echo
  echo ">>> Two benches on $model, about 10 minutes. Run it again to go on if it is cut off:"
  echo "    Files where a heading does not hold for every line, seed 111: 72 reviews, about \$0.09; it stops itself before \$0.15"
  echo "    The reworks on the held-out tapes, with and without what the verifier said: about \$0.08; it stops itself before \$0.15"
  echo "    Written before it ran: the heading sentence may lose at most 1 caught error of 18, and the reason must bring right"
  echo "    at least twice as many wrong products as the plain brief, and talk at most 1 right one wrong, or 5%."
  echo "    The full bars are at the top of this script."
  read -r -p "Run them now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  held refine-heading 0.15 verify-bench --seed 111 --setups independent-layered,independent-both --arms heading \
    --questions 6 --entities 20 --distractors 6 --context 8000
  tapes=""
  for seed in 101 102 103 104 105; do tapes="$tapes${tapes:+,}data/tapes/heldout-s$seed-10.jsonl,data/tapes/heldout-s$seed-20.jsonl"; done
  held refine-rework 0.15 rework-bench --workers 4 --tapes "$tapes"
  echo
  echo "Done. Results: data/compare/refine-*.json   Tapes: data/tapes/refine-*.jsonl"
  exit 0
fi
if [ "$mode" = heldout ]; then
  echo
  echo ">>> Questions the rule has never seen, on $model, about 2.5 hours. Run it again to go on if it is cut off:"
  echo "    5 seeds (101 to 105), each: 24 questions at 10 companies, about \$0.27, stops itself before \$0.42;"
  echo "      and 6 at 20 companies, about \$0.12, stops itself before \$0.20. Single, the told crew and genet, the rule on."
  echo "    Every new merge reviewed under the source rule alone and the rule, about \$0.50; it stops itself before \$0.85"
  echo "    The built products on seed 101, under the source rule alone and the rule, about \$0.08; it stops itself before \$0.15"
  echo "    Written before it ran: the rule must fail at most half as many right answers, and lose at most 1 caught error"
  echo "    or 5%, whichever is more. The full bar is at the top of this script."
  read -r -p "Run them now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  # Hours long: keep the machine from idling to sleep for as long as this script runs, and no longer.
  command -v caffeinate >/dev/null 2>&1 && caffeinate -i -w $$ >/dev/null 2>&1 &
  tapes=""
  for seed in 101 102 103 104 105; do
    held "heldout-s$seed-10" 0.42 compare --seed "$seed" --per-family 6 --entities 10 --distractors 6 \
      --strategies single,always-told,genet --context 8000 --tool-rounds 4 --verify-rule both
    held "heldout-s$seed-20" 0.20 compare --seed "$seed" --families aggregate,breadth --per-family 3 --entities 20 --distractors 6 \
      --strategies single,always-told,genet --context 8000 --tool-rounds 4 --verify-rule both
    tapes="$tapes${tapes:+,}data/tapes/heldout-s$seed-10.jsonl,data/tapes/heldout-s$seed-20.jsonl"
  done
  held heldout-merges 0.85 merge-bench --workers 4 --rules none,both --tapes "$tapes"
  held heldout-built 0.15 verify-bench --seed 101 --setups independent-layered,independent-both --arms split \
    --questions 6 --entities 20 --distractors 6 --context 8000
  echo
  echo "Done. Results: data/compare/heldout-*.json   Tapes: data/tapes/heldout-*.jsonl"
  exit 0
fi

if [ "$mode" = merges ]; then
  T=data/tapes
  tapes="$T/indep-20261102-104941.jsonl,$T/size-20261102-111758.jsonl,$T/fixes10-20261102-151115.jsonl,$T/fixes20-20261102-151115.jsonl,$T/second20-20261103-143113.jsonl,$T/wide10-20261102-114919.jsonl,$T/wide20-20261102-114919.jsonl,$T/crew10-20261102-125135.jsonl,$T/crew20-20261102-125135.jsonl"
  echo
  echo ">>> Two runs on $model, about 25 minutes:"
  echo "    The real merges: 123 reviews from the tapes, under 4 rules, 492 calls, 4 at a time, about \$0.56; it stops itself before \$0.85"
  echo "    The built products: 36, under the 2 new rules, 72 calls, about \$0.08; it stops itself before \$0.15"
  read -r -p "Run them now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  echo
  echo "== the real merges, under each rule"
  "$PY" -m taskorg.cli merge-bench --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.85 --workers 4 --tapes "$tapes" \
    --record "data/tapes/merges-$stamp.jsonl" --out "data/compare/merges-$stamp.json" 2>&1 \
    | tee "data/compare/merges-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^|---"
  echo
  echo "== the built products, under the two new rules"
  "$PY" -m taskorg.cli verify-bench --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.15 \
    --setups independent-headed,independent-both --arms split --questions 6 --entities 20 --distractors 6 --context 8000 \
    --record "data/tapes/split-rules-$stamp.jsonl" --out "data/compare/split-rules-$stamp.json" 2>&1 \
    | tee "data/compare/split-rules-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^|---"
  echo
  echo "Done. Results: data/compare/merges-$stamp.json and split-rules-$stamp.json   Tapes: data/tapes/merges-$stamp.jsonl and split-rules-$stamp.jsonl"
  exit 0
fi

if [ "$mode" = next ]; then
  echo
  echo ">>> Two runs on $model, about 12 minutes:"
  echo "    The second plan: 18 first plans the gates refuse, and the lead's next, about \$0.02; it stops itself before \$0.05"
  echo "    The verifier: 72 reviews of products shaped like a merge, with and without the note, about \$0.08; it stops itself before \$0.15"
  read -r -p "Run them now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  echo
  echo "== the second plan"
  "$PY" -m taskorg.cli plan-bench --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.05 \
    --record "data/tapes/plan-$stamp.jsonl" --out "data/compare/plan-$stamp.json" 2>&1 \
    | tee "data/compare/plan-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^|---"
  echo
  echo "== the verifier on split-shaped products, told and not told its sources are a sample"
  "$PY" -m taskorg.cli verify-bench --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.15 \
    --setups independent-layered,independent-told --arms split --questions 6 --entities 20 --distractors 6 --context 8000 \
    --record "data/tapes/split-verify-$stamp.jsonl" --out "data/compare/split-verify-$stamp.json" 2>&1 \
    | tee "data/compare/split-verify-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^|---"
  echo
  echo "Done. Results: data/compare/plan-$stamp.json and split-verify-$stamp.json   Tapes: data/tapes/plan-$stamp.jsonl and split-verify-$stamp.jsonl"
  exit 0
fi

if [ "$mode" = second ]; then
  echo
  echo ">>> One run on $model, about 5 minutes:"
  echo "    20 companies: 6 genet trials, aggregate and breadth, about \$0.06; it stops itself before \$0.10"
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  echo
  echo "== genet with a second plan and a sub-agent's own room, 20 companies"
  "$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.10 \
    --families aggregate,breadth --per-family 3 --entities 20 --distractors 6 --strategies genet --context 8000 --tool-rounds 4 \
    --record "data/tapes/second20-$stamp.jsonl" --out "data/compare/second20-$stamp.json" 2>&1 \
    | tee "data/compare/second20-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
  echo
  echo "Done. Results: data/compare/second20-$stamp.json   Tape: data/tapes/second20-$stamp.jsonl"
  exit 0
fi

if [ "$mode" = fixes ]; then
  echo
  echo ">>> Two runs on $model, about 15 minutes:"
  echo "    10 companies: 24 genet trials, all 4 question types (the wide run's questions), about \$0.11; it stops itself before \$0.22"
  echo "    20 companies: 6 genet trials, aggregate and breadth, about \$0.06; it stops itself before \$0.10"
  read -r -p "Run them now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  echo
  echo "== genet with the fixes, 10 companies"
  "$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.22 \
    --per-family 6 --entities 10 --distractors 6 --strategies genet --context 8000 --tool-rounds 4 \
    --record "data/tapes/fixes10-$stamp.jsonl" --out "data/compare/fixes10-$stamp.json" 2>&1 \
    | tee "data/compare/fixes10-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
  echo
  echo "== genet with the fixes, 20 companies"
  "$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.10 \
    --families aggregate,breadth --per-family 3 --entities 20 --distractors 6 --strategies genet --context 8000 --tool-rounds 4 \
    --record "data/tapes/fixes20-$stamp.jsonl" --out "data/compare/fixes20-$stamp.json" 2>&1 \
    | tee "data/compare/fixes20-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
  echo
  echo "Done. Results: data/compare/fixes10-$stamp.json and fixes20-$stamp.json   Tapes: data/tapes/fixes10-$stamp.jsonl and fixes20-$stamp.jsonl"
  exit 0
fi

if [ "$mode" = crew ]; then
  echo
  echo ">>> Two runs on $model, about 10 minutes:"
  echo "    10 companies: 24 trials, all 4 question types (the same questions as the wide run), the told crew, about \$0.15; it stops itself before \$0.25"
  echo "    20 companies: 6 trials, the same, about \$0.05; it stops itself before \$0.12"
  read -r -p "Run them now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  echo
  echo "== the told crew, 10 companies"
  "$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.25 \
    --per-family 6 --entities 10 --distractors 6 --strategies always-told --context 8000 --tool-rounds 4 \
    --record "data/tapes/crew10-$stamp.jsonl" --out "data/compare/crew10-$stamp.json" 2>&1 \
    | tee "data/compare/crew10-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
  echo
  echo "== the told crew, 20 companies"
  "$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.12 \
    --families aggregate,breadth --per-family 3 --entities 20 --distractors 6 --strategies always-told --context 8000 --tool-rounds 4 \
    --record "data/tapes/crew20-$stamp.jsonl" --out "data/compare/crew20-$stamp.json" 2>&1 \
    | tee "data/compare/crew20-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
  echo
  echo "Done. Results: data/compare/crew10-$stamp.json and crew20-$stamp.json   Tapes: data/tapes/crew10-$stamp.jsonl and crew20-$stamp.jsonl"
  exit 0
fi

if [ "$mode" = wide ]; then
  echo
  echo ">>> Two runs on $model, about 40 minutes:"
  echo "    10 companies: 72 trials, 4 question types, single, crew and genet, about \$0.30; it stops itself before \$0.50"
  echo "    20 companies: 18 trials, aggregate and breadth, the same 3 strategies, about \$0.15; it stops itself before \$0.25"
  read -r -p "Run them now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  echo
  echo "== 10 companies, all four question types"
  "$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.50 \
    --per-family 6 --entities 10 --distractors 6 --strategies single,always,genet --context 8000 --tool-rounds 4 \
    --record "data/tapes/wide10-$stamp.jsonl" --out "data/compare/wide10-$stamp.json" 2>&1 \
    | tee "data/compare/wide10-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
  echo
  echo "== 20 companies, aggregate and breadth"
  "$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.25 \
    --families aggregate,breadth --per-family 3 --entities 20 --distractors 6 --strategies single,always,genet --context 8000 --tool-rounds 4 \
    --record "data/tapes/wide20-$stamp.jsonl" --out "data/compare/wide20-$stamp.json" 2>&1 \
    | tee "data/compare/wide20-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
  echo
  echo "Done. Results: data/compare/wide10-$stamp.json and wide20-$stamp.json   Tapes: data/tapes/wide10-$stamp.jsonl and wide20-$stamp.jsonl"
  exit 0
fi

if [ "$mode" = size ]; then
  echo
  echo ">>> One run on $model:"
  echo "    8 genet trials, the 10-file questions twice each at an 8,000-token cap, the lead told what the files come to;"
  echo "    about \$0.05; it stops itself before \$0.10"
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  echo
  echo "== split runs, the lead told the total"
  "$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.10 \
    --families aggregate --per-family 4 --repeat 2 --entities 10 --distractors 6 --strategies genet \
    --context 8000 --tool-rounds 4 \
    --record "data/tapes/size-$stamp.jsonl" --out "data/compare/size-$stamp.json" 2>&1 \
    | tee "data/compare/size-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
  echo
  echo "Done. Results: data/compare/size-$stamp.json   Tape: data/tapes/size-$stamp.jsonl"
  exit 0
fi

if [ "$mode" = independent ]; then
  echo
  echo ">>> One run on $model:"
  echo "    8 genet trials, the 10-file questions twice each at an 8,000-token cap, the verifier in the independent view;"
  echo "    about \$0.05; it stops itself before \$0.10"
  read -r -p "Run it now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  echo
  echo "== split runs, independent view"
  "$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.10 \
    --families aggregate --per-family 4 --repeat 2 --entities 10 --distractors 6 --strategies genet \
    --context 8000 --tool-rounds 4 --verify-view independent \
    --record "data/tapes/indep-$stamp.jsonl" --out "data/compare/indep-$stamp.json" 2>&1 \
    | tee "data/compare/indep-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
  echo
  echo "Done. Results: data/compare/indep-$stamp.json   Tape: data/tapes/indep-$stamp.jsonl"
  exit 0
fi

if [ "$mode" = followup ]; then
  echo
  echo ">>> Two runs on $model:"
  echo "    grouped plans: the 8 cards trials again, with the group note, about \$0.06; it stops itself before \$0.12"
  echo "    the false note, its file opened: 12 reviews under shared-full, about \$0.03; it stops itself before \$0.06"
  read -r -p "Run them now? [y/N]: " go
  case "$go" in
    y|Y|yes|Yes|YES) ;;
    *) echo "Not run."; exit 0 ;;
  esac
  echo
  echo "== grouped plans"
  "$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.12 \
    --families aggregate --per-family 4 --entities 10 --distractors 6 --strategies genet,genet-cards \
    --context 8000 --tool-rounds 4 \
    --record "data/tapes/grouped-$stamp.jsonl" --out "data/compare/grouped-$stamp.json" 2>&1 \
    | tee "data/compare/grouped-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
  echo
  echo "== the false note, its file opened"
  "$PY" -m taskorg.cli verify-bench --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.06 \
    --setups shared-full --arms note \
    --record "data/tapes/note-full-$stamp.jsonl" --out "data/compare/note-full-$stamp.json" 2>&1 \
    | tee "data/compare/note-full-$stamp.log" | grep --line-buffered -E "^\[|^\| |stopped|interrupted|^tape|^saved|^note" | grep --line-buffered -v "^| setup\|^|---"
  echo
  echo "Done. Results: data/compare/grouped-$stamp.json and note-full-$stamp.json   Tapes: data/tapes/grouped-$stamp.jsonl and note-full-$stamp.jsonl"
  exit 0
fi

echo
echo ">>> Three runs on $model:"
echo "    report bench: 48 sub-agent parts, about \$0.04; it stops itself before \$0.10"
echo "    cards: 8 genet trials, half with the members table, about \$0.05; it stops itself before \$0.12"
echo "    verifier arms: 36 reviews, a note that argues and planted instructions, about \$0.03; it stops itself before \$0.10"
read -r -p "Run them now? [y/N]: " go
case "$go" in
  y|Y|yes|Yes|YES) ;;
  *) echo "Not run."; exit 0 ;;
esac

echo
echo "== report bench"
"$PY" -m taskorg.cli report-bench --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.10 \
  --record "data/tapes/report-$stamp.jsonl" --out "data/compare/report-$stamp.json" 2>&1 \
  | tee "data/compare/report-$stamp.log" | grep --line-buffered -E "^\[|^\| |stopped|interrupted|^tape|^saved|^Parts" | grep --line-buffered -v "^| setup\|^|---"

echo
echo "== cards"
"$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.12 \
  --families aggregate --per-family 4 --entities 10 --distractors 6 --strategies genet,genet-cards \
  --context 8000 --tool-rounds 4 \
  --record "data/tapes/cards-$stamp.jsonl" --out "data/compare/cards-$stamp.json" 2>&1 \
  | tee "data/compare/cards-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
echo
echo "== verifier arms"
"$PY" -m taskorg.cli verify-bench --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.10 \
  --setups shared-layered --arms note,planted \
  --record "data/tapes/arms-$stamp.jsonl" --out "data/compare/arms-$stamp.json" 2>&1 \
  | tee "data/compare/arms-$stamp.log" | grep --line-buffered -E "^\[|^\| |stopped|interrupted|^tape|^saved|^note|^planted" | grep --line-buffered -v "^| setup\|^|---"
echo
echo "Done. Results: data/compare/report-$stamp.json, cards-$stamp.json and arms-$stamp.json   Tapes: data/tapes/report-$stamp.jsonl, cards-$stamp.jsonl and arms-$stamp.jsonl"
