#!/usr/bin/env bash
# check_mirror.sh — verify kit/ and skill-package/kit/ are byte-identical
# (the publish flow requires it: skill-package is what ships to the Hub repo
# and the marketplace PR; a drifted mirror = stale published kit).
# Usage: bash kit/tools/check_mirror.sh   (from anywhere; exits 1 on drift)
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if diff -r --exclude='__pycache__' "$REPO/kit" "$REPO/skill-package/kit" >/tmp/mirror-drift.txt 2>&1; then
  echo "check_mirror: kit/ == skill-package/kit/ (byte-identical) — OK"
  exit 0
else
  echo "check_mirror: DRIFT between kit/ and skill-package/kit/:" >&2
  head -30 /tmp/mirror-drift.txt >&2
  echo "..." >&2
  echo "fix: rsync -a --delete --exclude='__pycache__' $REPO/kit/ $REPO/skill-package/kit/ && re-run" >&2
  exit 1
fi
