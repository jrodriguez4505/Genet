#!/bin/bash
# The verify bench on Claude: does the verifier catch a wrong product? One key entry, one confirmation, one capped run.
#
#   bash scripts/verify_runs.sh
#
# 24 products for 20-company aggregate questions, 12 with one planted error (a look-alike's figure, or a
# wrong-year one), each reviewed under 5 setups: today's verifier, and the verifier given the sources
# (full or layered) with the shared view or the independent one. Only the verifier's calls go to the model.
#
# The key lives only in this process and the Python it starts: not in shell history, not on any command
# line, not in a log, a tape or a results file.
set -u
cd "$(dirname "$0")/.." || exit 1
PY="${PYTHON:-.venv/bin/python}"
if ! "$PY" -c "import anthropic" 2>/dev/null; then
  echo "Needs the SDK in $PY: python3 -m venv .venv && .venv/bin/pip install -e '.[anthropic]'"
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_PROFILE ANTHROPIC_CUSTOM_HEADERS TASKORG_ANTHROPIC_BASE

# Estimate from the sim's token counts, scaled by how Claude counts (1.75x) and its system prompt.
echo "Genet verify bench on Claude. Prices per million tokens, input / output:"
echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   about \$0.20 for 120 reviews, capped at \$0.40"
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
  --strategies single --context 200000 --max-spend 0.05 --out "data/compare/verify-smoke-$stamp.json" >/dev/null 2>&1
"$PY" -I - "data/compare/verify-smoke-$stamp.json" <<'EOF' || { echo "Smoke test did not pass. Nothing more was run."; exit 1; }
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
echo ">>> One run on $model: 120 reviews of 24 products, 12 of them wrong, about \$0.20; it stops itself before \$0.40."
read -r -p "Run it now? [y/N]: " go
case "$go" in
  y|Y|yes|Yes|YES) ;;
  *) echo "Not run."; exit 0 ;;
esac

echo
echo "== verify bench"
"$PY" -m taskorg.cli verify-bench --adapter anthropic --price-in "$pin" --price-out "$pout" --max-spend 0.40 \
  --record "data/tapes/verify-$stamp.jsonl" --out "data/compare/verify-$stamp.json" 2>&1 \
  | tee "data/compare/verify-$stamp.log" | grep --line-buffered -E "^\[|^\| |stopped|interrupted|^tape|^saved|^Reviews" | grep --line-buffered -v "^| setup\|^|---"
echo
echo "Done. Results: data/compare/verify-$stamp.json   Tape: data/tapes/verify-$stamp.jsonl"
