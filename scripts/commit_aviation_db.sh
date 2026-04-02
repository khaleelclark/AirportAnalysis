#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DB_PATH="data/aviation.db"
COMMIT_MESSAGE="${COMMIT_MESSAGE:-Data update}"
PUSH_CHANGES="${PUSH_CHANGES:-1}"
REMOTE_NAME="${REMOTE_NAME:-origin}"
BRANCH_NAME="${BRANCH_NAME:-$(git rev-parse --abbrev-ref HEAD)}"

mkdir -p logs

if command -v flock >/dev/null 2>&1; then
  exec 9>"$ROOT_DIR/logs/commit_aviation_db.lock"
  if ! flock -n 9; then
    echo "=== DB COMMIT $(date -u) === skipped (lock held)" >> "$ROOT_DIR/logs/db_commit.log"
    exit 0
  fi
fi

{
  echo "=== DB COMMIT $(date -u) ==="

  if [[ ! -f "$DB_PATH" ]]; then
    echo "skipped: $DB_PATH not found"
    exit 0
  fi

  git add "$DB_PATH"

  if git diff --cached --quiet -- "$DB_PATH"; then
    echo "skipped: no staged changes for $DB_PATH"
    exit 0
  fi

  git commit -m "$COMMIT_MESSAGE" -- "$DB_PATH"
  echo "committed: $COMMIT_MESSAGE"

  if [[ "$PUSH_CHANGES" == "1" ]]; then
    git push "$REMOTE_NAME" "$BRANCH_NAME"
    echo "pushed: $REMOTE_NAME/$BRANCH_NAME"
  else
    echo "push skipped: PUSH_CHANGES=$PUSH_CHANGES"
  fi

  echo ""
} >> "$ROOT_DIR/logs/db_commit.log" 2>&1
