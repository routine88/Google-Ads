#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

echo "== Checking GitHub for updates =="
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if ! git remote update origin; then
    echo "Warning: Unable to reach origin for updates."
  else
    if [ -z "$(git status --porcelain)" ]; then
      if ! git pull --ff-only origin main; then
        echo "Fast-forward failed; attempting rebase pull."
        git pull --rebase --autostash origin main || echo "Auto-update skipped."
      fi
    else
      echo "Local changes detected; skipping automatic merge."
    fi
  fi
else
  echo "Not a git repository; skipping update."
fi

echo "== Setting up Python environment =="
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "== Installing dependencies =="
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

echo "== Launching Google Ads AI GUI =="
python gui_app.py
