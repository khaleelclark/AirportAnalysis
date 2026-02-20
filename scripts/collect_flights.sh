#!/usr/bin/env bash
set -e
cd /home/khaleel/PycharmProjects/CapstoneProject
source .venv/bin/activate
mkdir -p logs
echo "=== FLIGHTS $(date -u) ===" >> logs/flights.log
python src/collect_flights.py >> logs/flights.log 2>&1
echo "" >> logs/flights.log
