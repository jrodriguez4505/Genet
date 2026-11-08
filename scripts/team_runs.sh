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
  all|followup|independent|size|wide|crew|fixes|second|next|merges|heldout|refine|whole|rerun|gaprule|aside|gapcheck|sonnet|sonnettwo|agents) ;;
  *) echo "Usage: bash scripts/team_runs.sh [followup|independent|size|wide|crew|fixes|second|next|merges|heldout|refine|whole|rerun|gaprule|aside|gapcheck|sonnet|sonnettwo|agents]. Nothing was run."; exit 1 ;;
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
if [ "$mode" = agents ]; then
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
  if [ "$mode" = sonnet ] || [ "$mode" = sonnettwo ]; then
    model=claude-sonnet-5-5; pin=2; pout=10
  else
    model=claude-haiku-5-5; pin=0.10; pout=0.50
  fi
  echo "Using the key this window holds, on $model. No smoke test: nothing is spent before your y."
else
  session=""
  pick=""
  want=1; { [ "$mode" = sonnet ] || [ "$mode" = sonnettwo ]; } && want=2
  while [ -z "$pick" ]; do
    read -r -p "Model, type $want: " pick
  done
  case "$mode:$pick" in
    sonnet:2|sonnettwo:2) model=claude-sonnet-5-5; pin=2; pout=10 ;;
    sonnet:*|sonnettwo:*) echo "This run is on Sonnet: type 2. Nothing was run."; exit 1 ;;
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

if [ "$mode" = heldout ] || [ "$mode" = refine ] || [ "$mode" = whole ] || [ "$mode" = rerun ] || [ "$mode" = gaprule ] || [ "$mode" = aside ] || [ "$mode" = gapcheck ] || [ "$mode" = sonnet ] || [ "$mode" = sonnettwo ] || [ "$mode" = agents ]; then
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
