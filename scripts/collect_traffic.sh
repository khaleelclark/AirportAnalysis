#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/.venv/bin/activate"
mkdir -p logs
if command -v flock >/dev/null 2>&1; then
  exec 9>"$ROOT_DIR/logs/collect_traffic.lock"
  if ! flock -n 9; then
    echo "=== TRAFFIC $(date -u) === skipped (lock held)" >> "$ROOT_DIR/logs/traffic.log"
    exit 0
  fi
fi
echo "=== TRAFFIC $(date -u) ===" >> logs/traffic.log
python src/collect_traffic.py >> logs/traffic.log 2>&1
echo "" >> logs/traffic.log
