#!/bin/bash
# Runs the Kindle News Filter pipeline once a day, however many times it is
# called. Meant to be started several times a day by the Claude desktop
# scheduled task, but safe to run by hand too.
#
#   1. Exit at once if today's edition was already sent (pipeline log).
#   2. Exit at once if another run is still going.
#   3. Start Ollama if it is not running.
#   4. Run the pipeline.
#
# Exit codes: 0 = sent now or already sent today, 1 = failed (the next
# scheduled slot will try again), 2 = another run is in progress.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

TODAY="$(date +%Y-%m-%d)"
RUN_LOG="state/run.log"
LOCK_DIR="state/run.lock"

if [ -f "$RUN_LOG" ] && grep -q "Sent edition for $TODAY " "$RUN_LOG"; then
    echo "Edition for $TODAY already sent, nothing to do."
    exit 0
fi

mkdir -p state
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    # A lock older than 2 hours is a crashed run, not a live one.
    if [ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +120)" ]; then
        rmdir "$LOCK_DIR"
        mkdir "$LOCK_DIR"
    else
        echo "Another run is in progress, skipping."
        exit 2
    fi
fi
trap 'rmdir "$LOCK_DIR"' EXIT

if ! curl -s -m 3 http://localhost:11434/api/tags > /dev/null; then
    echo "Ollama is not running, starting it."
    open -a Ollama
    for _ in $(seq 1 30); do
        sleep 2
        curl -s -m 3 http://localhost:11434/api/tags > /dev/null && break
    done
    if ! curl -s -m 3 http://localhost:11434/api/tags > /dev/null; then
        echo "Ollama did not start in 60 seconds." >&2
        exit 1
    fi
fi

source .venv/bin/activate
python src/main.py
