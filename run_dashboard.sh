#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${WORKDIR}/frontend"

echo "Starting Job Watch backend + frontend..."

cd "${WORKDIR}"

# Start FastAPI uvicorn server in background
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
