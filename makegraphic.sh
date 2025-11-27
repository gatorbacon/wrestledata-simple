#!/bin/bash

# bail out if no argument
if [ -z "$1" ]; then
  echo "Usage: bash makegraphic.sh <weight>"
  exit 1
fi

WEIGHT="$1"

# run both commands
.venv/bin/python scripts/rankings/top10_from_template.py \
  -season 2026 \
  -weight-class "$WEIGHT" \
  -images-dir assets/wrestler_photos \
  -out-base "mt/graphics/2026/top10_${WEIGHT}"

.venv/bin/python scripts/rankings/matrix_top33_graphic.py \
  -season 2026 \
  -weight-class "$WEIGHT" \
  -output "mt/graphics/2026/matrix_${WEIGHT}_top33.jpg"