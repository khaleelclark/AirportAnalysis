#!/usr/bin/env bash
set -e
cd /home/khaleel/PycharmProjects/CapstoneProject
source .venv/bin/activate
mkdir -p logs
echo "=== DELAYS $(date -u) ===" >> logs/delays.log
python src/collect_delays.py >> logs/delays.log 2>&1
echo "" >> logs/delays.log
