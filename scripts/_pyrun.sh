#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Ưu tiên .venv của chính repo (chắc chắn có đủ dependency, vd python-dotenv
# mà submit_log.py cần để đọc AI_LOG_SERVER từ .env); nếu không có mới dò
# python3 → python → py -3 trên PATH; trên Windows, fallback về các vị trí cài
# Python phổ biến vì Git Bash launched by some hooks gets a stripped PATH that
# omits the Windows Python directory.
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

# Bug thật gặp phải: PATH có thể trỏ `python` sang một venv KHÁC của repo (vd
# frontend/.venv) thiếu python-dotenv — submit_log.py nuốt ImportError âm
# thầm, AI_LOG_SERVER đọc ra rỗng, log AI bắt buộc của BTC không được gửi mà
# không có cảnh báo rõ ràng. Ưu tiên .venv gốc repo để tránh lặp lại.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

PY=""
for venv_py in "$REPO_ROOT/.venv/Scripts/python.exe" "$REPO_ROOT/.venv/bin/python"; do
  if [ -x "$venv_py" ] && is_real_python "$venv_py"; then
    PY="$venv_py"
    break
  fi
done

if [ -n "$PY" ]; then
  : # đã tìm được .venv gốc repo, dùng luôn
elif command -v python3 >/dev/null 2>&1 && is_real_python python3; then
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
