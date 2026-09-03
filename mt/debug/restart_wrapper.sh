#!/bin/bash
# Usage: restart_wrapper.sh <worker_id> <season> <exit_after>
# Runs the debug scraper in a loop: if it exits with code 2 (our "hit the
# consecutive-failure threshold" signal), relaunch a brand-new process
# immediately with no cooldown. Any other exit code stops the loop.
WORKER_ID=$1
SEASON=$2
EXIT_AFTER=$3
LOG="/tmp/debug${SEASON}_restart_${WORKER_ID}.log"
cd /Users/tjthompson/Documents/Cursor/wrestledata-simple

while true; do
  .venv/bin/python -u wrestle_scraper_debug.py -season "$SEASON" -league ncaa -gender men \
    -headless -full-run -exit-after "$EXIT_AFTER" -worker-id "$WORKER_ID" >> "$LOG" 2>&1
  code=$?
  if [ $code -ne 2 ]; then
    echo "=== [$WORKER_ID] process exited with code $code (not a restart trigger) -- stopping wrapper loop ===" >> "$LOG"
    break
  fi
  echo "=== [$WORKER_ID] process exited with code 2 (restart trigger) -- relaunching immediately, no cooldown ===" >> "$LOG"
done
