#!/bin/bash
# Runs the Kindle News Filter pipeline once. Meant to be invoked by the
# com.seba.kindlenews launchd job (see scripts/com.seba.kindlenews.plist),
# but safe to run by hand too.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

source .venv/bin/activate
exec python src/main.py
