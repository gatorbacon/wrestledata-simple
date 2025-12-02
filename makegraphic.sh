#!/bin/bash

# bail out if not enough arguments
if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: bash makegraphic.sh <weight> <delta-days>"
  exit 1
fi

WEIGHT="$1"
DELTA_DAYS="$2"

# run both commands
.venv/bin/python scripts/rankings/top10_from_template.py \
  -season 2026 \
  -weight-class "$WEIGHT" \
  -images-dir assets/wrestler_photos \
  -out-base "mt/graphics/2026/top10_${WEIGHT}" \
  -delta-days "$DELTA_DAYS"

.venv/bin/python scripts/rankings/matrix_top33_graphic.py \
  -season 2026 \
  -weight-class "$WEIGHT" \
  -output "mt/graphics/2026/matrix_${WEIGHT}_top33.jpg" \
  -delta-days "$DELTA_DAYS"