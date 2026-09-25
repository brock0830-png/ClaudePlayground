#!/usr/bin/env bash
# Full SCALPEL-W-v42 in-sample pipeline (no 2021+ data is read).
set -euo pipefail
cd "$(dirname "$0")/src"
python3 canary.py
python3 grid.py real
for m in shift-0.30 shift-0.15 shift0.15 shift0.30; do python3 grid.py $m & done; wait
for m in scale0.95 scale1.05 slip2; do python3 grid.py $m & done; wait
python3 placebo_compare.py
python3 families.py round1
python3 families.py round2
python3 families.py round3
echo PIPELINE_DONE
