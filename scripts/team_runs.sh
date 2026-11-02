#!/bin/bash
# Two small team measurements on Claude. One key entry, one confirmation, each run capped.
#
#   bash scripts/team_runs.sh            the three runs below
#   bash scripts/team_runs.sh followup   the two follow-ups to them (2 November, docs/LIVE_TESTS.md):
#     - the cards again, now that a lead on a tight cap is told how to name a group's files;
#     - the false note under shared-full, which opens the file the note cites. The independent view's brief
#       is the same with or without the note, so its 29 October tape already answers for it.
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
# line, not in a log, a tape or a results file.
set -u
mode="${1:-all}"
case "$mode" in
  all|followup) ;;
  *) echo "Usage: bash scripts/team_runs.sh [followup]. Nothing was run."; exit 1 ;;
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
if [ "$mode" = followup ]; then
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.09 in all, each run capped (\$0.18 in all, and the smoke test)"
else
  echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.12 in all, each run capped (\$0.37 in all)"
fi
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
export TASKORG_ANTHROPIC_KEY="$key" TASKORG_MODEL_NAME="$model" TASKORG_MODEL_EFFORT=low
unset key
echo "Key received (${#TASKORG_ANTHROPIC_KEY} characters, not shown)."

stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p data/compare data/tapes

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
