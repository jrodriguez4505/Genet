#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pytest -q tests
echo
echo "Fixtures green. Invariants held."
