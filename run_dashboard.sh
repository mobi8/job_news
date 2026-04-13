#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${WORKDIR}/frontend"
SKIP_SCRAPE="${NO_SCRAPE:-0}"
JOBS_DIR="${WORKDIR}/outputs"

echo "Starting Job Watch backend + frontend..."

# Kill existing processes on ports
kill $(lsof -ti:8000 2>/dev/null) 2>/dev/null || true
kill $(lsof -ti:5173 2>/dev/null) 2>/dev/null || true
sleep 0.5

# Frontend cleanup & rebuild
cd "${FRONTEND_DIR}"
rm -rf node_modules/.vite dist 2>/dev/null || true
if [[ ! -d node_modules ]]; then
  echo "Installing dependencies..."
  npm install --silent 2>/dev/null
fi

# Check required files
if [[ ! -f "${JOBS_DIR}/jobs_analysis.json" ]] || [[ ! -f "${JOBS_DIR}/job_stats_data.json" ]]; then
  echo "⚠️  Data files missing. Run scraper first or use: NO_SCRAPE=1 bash run_dashboard.sh"
  exit 1
fi

# Create job_statuses.json if missing
if [[ ! -f "${JOBS_DIR}/job_statuses.json" ]]; then
  echo '{"statuses": {}}' > "${JOBS_DIR}/job_statuses.json"
fi

if [[ "${SKIP_SCRAPE}" != "1" ]]; then
  echo "Running scraper..."
  python3 src/watch/scraper.py collect || echo "Scraper error (continuing)"
fi

cd "${WORKDIR}"
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
