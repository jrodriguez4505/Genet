#!/bin/bash
# One key entry for a sitting of live runs, so each run needs only your y.
#
#   bash scripts/live_session.sh [mode]     mode, if given, is the first run to ask you about
#
# The key stays in this script's memory: not in a file, not in shell history, not on any command line, and handed
# only to the run you approve. Ctrl-C, closing the window or restarting the app forgets it.
#
# A run is asked for by writing its mode to data/.live-request, one of scripts/team_runs.sh's. Asking spends nothing:
# the run shows its estimate and caps, and starts only when you type y here. Say no, and this goes on waiting.
set -u
cd "$(dirname "$0")/.." || exit 1
request=data/.live-request
mkdir -p data
rm -f "$request"  # a request left from an earlier sitting is not a request
first="${1:-}"
read -r -s -p "Anthropic API key (typing is hidden; paste and press Enter): " key
echo
if [ -z "$key" ]; then
  echo "No key entered. Nothing was run."
  exit 1
fi
echo "Key received (${#key} characters, not shown). It stays in this window; Ctrl-C or closing it forgets the key."
while :; do
  if [ -n "$first" ]; then
    mode=$first
    first=""
  else
    echo
    echo "Waiting for a run to be asked for. Nothing runs until you type y here."
    until [ -s "$request" ]; do sleep 1; done
    mode=$(head -n 1 "$request" | tr -cd 'a-z')
    rm -f "$request"
    printf '\a'
  fi
  echo
  echo ">>> Asked to run: $mode"
  GENET_LIVE_SESSION=1 TASKORG_ANTHROPIC_KEY="$key" bash scripts/team_runs.sh "$mode"
  [ -n "${GENET_SESSION_ONCE:-}" ] && break
done
