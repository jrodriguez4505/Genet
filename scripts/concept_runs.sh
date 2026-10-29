#!/bin/bash
# The concept experiments on Claude: one key entry, one confirmation, five runs, each with its own cap and tape.
#
#   bash scripts/concept_runs.sh                   # both arms: five runs, 128 trials, about $0.75
#   bash scripts/concept_runs.sh aggregate-rerun   # single and genet on aggregate, 5, 10 and 20 companies, twice
#
# Arm 1, "is a second agent doing new work?": aggregate and breadth questions where some companies' figures
# are already filed and checked. A crew staffs those parts anyway; Genet's first gate refuses them.
# Arm 2, "should we?": the same questions over 5, 10 and 20 companies, with extra wrong-year figures, at a
# roomy cap, run twice. Where a single agent's accuracy falls and a crew's holds is a measured reason to split.
#
# The key lives only in this process and the Python it starts: not in shell history, not on any command
# line, not in a log, a tape or a results file.
set -u
plan="${1:-all}"
case "$plan" in
  all|aggregate-rerun) ;;
  *) echo "Plans: all, aggregate-rerun"; exit 1 ;;
esac
cd "$(dirname "$0")/.." || exit 1
PY="${PYTHON:-.venv/bin/python}"
if ! "$PY" -c "import anthropic" 2>/dev/null; then
  echo "Needs the SDK in $PY: python3 -m venv .venv && .venv/bin/pip install -e '.[anthropic]'"
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_PROFILE ANTHROPIC_CUSTOM_HEADERS TASKORG_ANTHROPIC_BASE

# Estimates from a rehearsal against a stand-in that counts and replies like Haiku 5.5 did.
echo "Genet concept experiments on Claude. Prices per million tokens, input / output; cost of all five runs:"
echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.75, each run capped, \$1.35 at most"
echo "  2) claude-sonnet-5-5   \$2 / \$10        about \$15: more than this script allows; run Haiku first"
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
common=(--adapter anthropic --price-in "$pin" --price-out "$pout" --families aggregate,breadth --per-family 2
        --strategies single,always,genet,genet-stated --context 200000 --tool-rounds 4 --distractors 6)

echo
echo "== Smoke test: one lookup task, single agent (capped at \$0.05)"
"$PY" -m taskorg.cli compare --adapter anthropic --price-in "$pin" --price-out "$pout" --per-family 1 --families lookup \
  --strategies single --context 200000 --max-spend 0.05 --out "data/compare/concept-smoke-$stamp.json" >/dev/null 2>&1
"$PY" -I - "data/compare/concept-smoke-$stamp.json" <<'EOF' || { echo "Smoke test did not pass. Nothing more was run."; exit 1; }
import json, sys
try:
    r = json.load(open(sys.argv[1]))["results"][0]
except (OSError, ValueError, KeyError, IndexError) as e:
    sys.exit(f"no smoke result: {e}")
print(f"smoke: {r['status']}, answer {r['answer']!r} (expected {r['expected']!r}), {r['calls']} calls")
if r["calls"] == 0 or r["code"] in ("LIVE", "CRASH") or not r["correct"]:
    sys.exit("the smoke test did not get the right answer")
EOF

echo
if [ "$plan" = all ]; then
  echo ">>> Five runs on $model, 128 trials in all, about \$0.75; each stops itself before its cap:"
  echo "    arm 1: 6 companies with 3 filed (cap \$0.20); 10 with 5 filed (cap \$0.20)"
  echo "    arm 2: 5, 10 and 20 companies, each run twice (caps \$0.25, \$0.30, \$0.40)"
else
  echo ">>> Three runs on $model, 24 trials in all, about \$0.20; each stops itself before its cap:"
  echo "    single and genet on aggregate questions over 5, 10 and 20 companies, each run twice (caps \$0.08, \$0.12, \$0.20)"
fi
read -r -p "Run them now? [y/N]: " go
case "$go" in
  y|Y|yes|Yes|YES) ;;
  *) echo "Not run."; exit 0 ;;
esac

run() {  # name cap args...
  local name="$1" cap="$2"; shift 2
  echo
  echo "== $name"
  "$PY" -m taskorg.cli compare "${common[@]}" "$@" --max-spend "$cap" \
    --record "data/tapes/concept-$name-$stamp.jsonl" --out "data/compare/concept-$name-$stamp.json" 2>&1 \
    | tee "data/compare/concept-$name-$stamp.log" | grep --line-buffered -E "^\[|^\| |^- |stopped|interrupted|^tape|^saved" | grep --line-buffered -v "^| strategy\|^|---"
}
if [ "$plan" = all ]; then
  run arm1-6-filed3 0.20 --entities 6 --filed 3
  run arm1-10-filed5 0.20 --entities 10 --filed 5
  run arm2-5 0.25 --entities 5 --repeat 2
  run arm2-10 0.30 --entities 10 --repeat 2
  run arm2-20 0.40 --entities 20 --repeat 2
else
  common=(--adapter anthropic --price-in "$pin" --price-out "$pout" --families aggregate --per-family 2
          --strategies single,genet --context 200000 --tool-rounds 4 --distractors 6)
  run agg-5 0.08 --entities 5 --repeat 2
  run agg-10 0.12 --entities 10 --repeat 2
  run agg-20 0.20 --entities 20 --repeat 2
fi
echo
echo "Done. Results: data/compare/concept-*-$stamp.json   Tapes: data/tapes/concept-*-$stamp.jsonl"
