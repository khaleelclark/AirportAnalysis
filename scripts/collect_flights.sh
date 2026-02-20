#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/.venv/bin/activate"
mkdir -p logs
if command -v flock >/dev/null 2>&1; then
  exec 9>"$ROOT_DIR/logs/collect_flights.lock"
  if ! flock -n 9; then
    echo "=== FLIGHTS $(date -u) === skipped (lock held)" >> "$ROOT_DIR/logs/flights.log"
    exit 0
  fi
fi
echo "=== FLIGHTS $(date -u) ===" >> logs/flights.log
python src/collect_flights.py >> logs/flights.log 2>&1
echo "" >> logs/flights.log
