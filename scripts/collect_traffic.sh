#!/usr/bin/env bash
set -e
cd /home/khaleel/PycharmProjects/CapstoneProject
source .venv/bin/activate
mkdir -p logs
echo "=== TRAFFIC $(date -u) ===" >> logs/traffic.log
python src/collect_traffic.py >> logs/traffic.log 2>&1
echo "" >> logs/traffic.log
