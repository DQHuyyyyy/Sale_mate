#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Tries python3 → python → py -3 on PATH; on Windows, falls back to common
# Python install locations because Git Bash launched by some hooks gets a
# stripped PATH that omits the Windows Python directory.
# Designed to be sourced or called as: bash scripts/_pyrun.sh <script> [args...]
#
# Exits 0 silently if no Python is found — hooks must never block the AI tool.
set -u

# On Windows, `python`/`python3` on PATH can resolve to App Execution Alias
# stubs (AppData\Local\Microsoft\WindowsApps\python3.exe) that exist as a
# file — so `command -v` finds them — but don't run Python at all; they just
# print a Microsoft Store redirect and exit nonzero. Verify a candidate
# actually executes before trusting it, instead of trusting PATH lookup alone.
is_real_python() {
  "$@" -c "" >/dev/null 2>&1
}

PY=""
if command -v python3 >/dev/null 2>&1 && is_real_python python3; then
  PY=python3
elif command -v python >/dev/null 2>&1 && is_real_python python; then
  PY=python
elif command -v py >/dev/null 2>&1 && is_real_python py -3; then
  PY="py -3"
else
  # PATH lookup failed or found only broken stubs — probe standard Windows
  # install locations.
  PY=""
  shopt -s nullglob 2>/dev/null || true
  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    if [ -x "$cand" ]; then PY="$cand"; break; fi
  done
  shopt -u nullglob 2>/dev/null || true
  [ -n "$PY" ] || exit 0
fi

# shellcheck disable=SC2086
exec $PY "$@"
