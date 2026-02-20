#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/.venv/bin/activate"
mkdir -p logs
if command -v flock >/dev/null 2>&1; then
  exec 9>"$ROOT_DIR/logs/collect_delays.lock"
  if ! flock -n 9; then
    echo "=== DELAYS $(date -u) === skipped (lock held)" >> "$ROOT_DIR/logs/delays.log"
    exit 0
  fi
fi
echo "=== DELAYS $(date -u) ===" >> logs/delays.log
python src/collect_delays.py >> logs/delays.log 2>&1
echo "" >> logs/delays.log
