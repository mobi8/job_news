#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${WORKDIR}/frontend"

# 설정: NO_SCRAPE=1로 전달하면 스크래퍼는 건너뜁니다.
SKIP_SCRAPE="${NO_SCRAPE:-0}"

echo "Starting Job Watch backend + frontend..."

if [[ "${SKIP_SCRAPE}" != "1" ]]; then
  echo "Running scraper (python3 src/watch/scraper.py collect)..."
  python3 src/watch/scraper.py collect
fi

cd "${WORKDIR}"

# Start FastAPI uvicorn server in background
export PYTHONPATH="${WORKDIR}/src:${PYTHONPATH:-}"
uvicorn src.api.app:app --reload --log-level info &
UVICORN_PID=$!

cd "${FRONTEND_DIR}"
npx --yes vite &
VITE_PID=$!

cleanup() {
  echo "Shutting down..."
  kill "${VITE_PID}" "${UVICORN_PID}" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

wait "${VITE_PID}" "${UVICORN_PID}"
