#!/bin/bash
# The live pilot on Claude, with a spend cap and a tape.
#
#   bash scripts/live_pilot.sh
#
# Asks for a model and for the key without showing it, runs a one-task smoke test, and runs the pilot
# only if you answer y. Each run stops itself before it could pass its cap. Every exchange is saved
# to a tape under data/tapes/, so the run can be replayed later with no key and no spend:
#
#   .venv/bin/python -m taskorg.cli compare --replay data/tapes/<tape>.jsonl --per-family 2 \
#     --strategies single,always,genet,genet-stated
#
# The key lives only in this process and the Python it starts: not in shell history, not on any
# command line, not in a log, a tape or a results file.
set -u
cd "$(dirname "$0")/.." || exit 1
PY="${PYTHON:-.venv/bin/python}"
if ! "$PY" -c "import anthropic" 2>/dev/null; then
  echo "Needs the SDK in $PY: python3 -m venv .venv && .venv/bin/pip install -e '.[anthropic]'"
  exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
# Credentials, endpoints and headers set for other tools never reach these runs.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_PROFILE ANTHROPIC_CUSTOM_HEADERS TASKORG_ANTHROPIC_BASE

echo "Genet live pilot on Claude. Prices per million tokens, input / output:"
echo "  1) claude-haiku-5-5    \$0.10 / \$0.50   pilot about \$0.05, capped at \$0.50"
echo "  2) claude-sonnet-5-5   \$2 / \$10        pilot about \$0.60 to \$1.10, capped at \$2.00"
echo "  3) claude-opus-5-5     \$4 / \$20        pilot about \$1.20 to \$2.20, capped at \$3.50"
read -r -p "Model [1]: " pick
case "${pick:-1}" in
  1) model=claude-haiku-5-5;  pin=0.10; pout=0.50; cap=0.50 ;;
  2) model=claude-sonnet-5-5; pin=2;    pout=10;   cap=2.00 ;;
  3) model=claude-opus-5-5;   pin=4;    pout=20;   cap=3.50 ;;
  *) echo "No such choice. Nothing was run."; exit 1 ;;
esac
read -r -s -p "Anthropic API key (typing is hidden; paste and press Enter): " key
echo
if [ -z "$key" ]; then
  echo "No key entered. Nothing was run."
  exit 1
fi
export TASKORG_ANTHROPIC_KEY="$key" TASKORG_MODEL_NAME="$model" TASKORG_MODEL_EFFORT=low
unset key
echo "Key received (${#TASKORG_ANTHROPIC_KEY} characters, not shown). Model $model, effort low."

tag="${model#claude-}-$(date +%Y%m%d-%H%M%S)"
mkdir -p data/compare data/tapes
price=(--adapter anthropic --price-in "$pin" --price-out "$pout")

echo
echo "== Smoke test: one lookup task, single agent, about 3 calls (capped at \$0.10)"
"$PY" -m taskorg.cli compare "${price[@]}" --per-family 1 --families lookup --strategies single --max-spend 0.10 \
  --record "data/tapes/smoke-$tag.jsonl" --out "data/compare/smoke-$tag.json" 2>&1 | tee "data/compare/smoke-$tag.log"
"$PY" -I - "data/compare/smoke-$tag.json" <<'EOF' || { echo "Smoke test did not pass. The pilot was not run."; exit 1; }
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    r = data["results"][0]
except (OSError, ValueError, KeyError, IndexError) as e:
    sys.exit(f"no smoke result: {e}")
cost = data["summary"]["overall"]["single"].get("cost_total", 0)
print(f"smoke: status {r['status']}, code {r['code'] or 'none'}, answer {r['answer']!r} (expected {r['expected']!r}), "
      f"{r['calls']} calls, {r['tokens']} tokens, about ${cost:.4f}, "
      f"usage {'estimated' if r['tokens_estimated'] else 'reported by the API'}")
if r["calls"] == 0 or r["code"] in ("LIVE", "CRASH"):
    sys.exit("the API did not answer properly")
EOF

echo
echo "The pilot is 32 trials, about 188 calls. It stops itself before it could pass \$$cap."
read -r -p "Run the pilot now on $model? [y/N]: " go
case "$go" in
  y|Y|yes|Yes|YES) ;;
  *) echo "Pilot not run."; exit 0 ;;
esac

echo
echo "== Pilot: single, always, genet, genet-stated; 2 tasks per family"
"$PY" -m taskorg.cli compare "${price[@]}" --per-family 2 --strategies single,always,genet,genet-stated --max-spend "$cap" \
  --record "data/tapes/pilot-$tag.jsonl" --out "data/compare/pilot-$tag.json" 2>&1 | tee "data/compare/pilot-$tag.log"
echo
echo "Results: data/compare/pilot-$tag.json   Tape: data/tapes/pilot-$tag.jsonl"
echo "The Console's usage page has the billed amount; the cost column here is an estimate from the reported tokens."
