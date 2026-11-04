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
  all|followup|independent|size|wide|crew|fixes|second|next|merges|heldout) ;;
  *) echo "Usage: bash scripts/team_runs.sh [followup|independent|size|wide|crew|fixes|second|next|merges|heldout]. Nothing was run."; exit 1 ;;
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
if [ "$mode" = heldout ]; then
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
  model=claude-haiku-5-5; pin=0.10; pout=0.50
  echo "Using the key this window holds, on $model. No smoke test: nothing is spent before your y."
else
  session=""
  pick=""
  while [ -z "$pick" ]; do
    read -r -p "Model, type 1: " pick
  done
  case "$pick" in
    1) model=claude-haiku-5-5; pin=0.10; pout=0.50 ;;
    *) echo "Only Haiku runs from this script. Nothing was run."; exit 1 ;;
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

if [ "$mode" = heldout ]; then
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
      echo "$name did not finish, so nothing more was run. What finished is kept. To go on: bash scripts/team_runs.sh heldout"
      exit 1
    fi
    if grep -q '"stopped_after"' "data/compare/$name.json"; then
      echo "$name stopped early, at its cap or by you, so nothing more was run. What finished is kept. To run it again, move its results out of data/compare."
      exit 1
    fi
  }
  echo
  echo ">>> Questions the rule has never seen, on $model, about 2.5 hours. Run it again to go on if it is cut off:"
  echo "    5 seeds (101 to 105), each: 24 questions at 10 companies, about \$0.27, stops itself before \$0.42;"
  echo "      and 6 at 20 companies, about \$0.12, stops itself before \$0.20. Single, the told crew and genet, the rule on."
  echo "    Every new merge reviewed under today's rule and the rule, about \$0.50; it stops itself before \$0.85"
  echo "    The built products on seed 101, under today's rule and the rule, about \$0.08; it stops itself before \$0.15"
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
  held heldout-merges 0.85 merge-bench --workers 4 --rules today,both --tapes "$tapes"
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
