#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${WORKDIR}/frontend"
SKIP_SCRAPE="${NO_SCRAPE:-1}"
JOBS_DIR="${WORKDIR}/outputs"

UVICORN_PID=""
VITE_PID=""
WATCH_LOOP_PID=""
CLEANUP_IN_PROGRESS=0

export PYTHONPATH="${WORKDIR}/src:${PYTHONPATH:-}"

echo "Starting Job Watch backend + frontend + watch loop..."

# Kill existing processes on ports
if lsof -ti:8000 >/dev/null 2>&1; then
  echo "  Killing existing process on port 8000..."
  kill $(lsof -ti:8000) 2>/dev/null || true
fi
if lsof -ti:5173 >/dev/null 2>&1; then
  echo "  Killing existing process on port 5173..."
  kill $(lsof -ti:5173) 2>/dev/null || true
fi
sleep 0.5

# Frontend cleanup & rebuild
cd "${FRONTEND_DIR}"
rm -rf node_modules/.vite dist 2>/dev/null || true
if [[ ! -d node_modules ]]; then
  echo "  Installing dependencies..."
  npm install --silent 2>/dev/null
fi

# Create job_statuses.json if missing
if [[ ! -f "${JOBS_DIR}/job_statuses.json" ]]; then
  echo '{"statuses": {}}' > "${JOBS_DIR}/job_statuses.json"
fi

cd "${WORKDIR}"
if [[ "${SKIP_SCRAPE}" != "1" ]]; then
  echo "Running scraper..."
  python3 src/watch/scraper.py collect || echo "Scraper error (continuing)"
fi

# Check required files after an optional scrape run
if [[ ! -f "${JOBS_DIR}/jobs_analysis.json" ]] || [[ ! -f "${JOBS_DIR}/job_stats_data.json" ]]; then
  echo "⚠️  Data files missing. Run scraper first or use: NO_SCRAPE=1 bash run_dashboard.sh"
  exit 1
fi

# Start watch loop in background (daemon mode)
cd "${WORKDIR}"
python3 src/watch/loop.py > /tmp/watch_loop.log 2>&1 &
WATCH_LOOP_PID=$!
echo "  Watch loop started (PID: $WATCH_LOOP_PID)"

cd "${WORKDIR}"
uvicorn src.api.app:app --reload --log-level info &
UVICORN_PID=$!
echo "  Backend started (PID: $UVICORN_PID)"

cd "${FRONTEND_DIR}"
./node_modules/.bin/vite &
VITE_PID=$!
echo "  Frontend started (PID: $VITE_PID)"

# Wait for servers to be ready and find actual Vite port
sleep 2

# Extract actual Vite port (checks for any process bound to localhost:417x)
VITE_PORT=4173
for port in 4173 4174 4175 4176 4177; do
  if lsof -i :$port 2>/dev/null | grep -q LISTEN; then
    VITE_PORT=$port
    break
  fi
done

echo "✓ Dashboard ready at http://localhost:$VITE_PORT/"
open "http://localhost:$VITE_PORT/" 2>/dev/null || xdg-open "http://localhost:$VITE_PORT/" 2>/dev/null || echo "  Please open http://localhost:$VITE_PORT/ in your browser"

cleanup() {
  if [[ $CLEANUP_IN_PROGRESS -eq 1 ]]; then
    return
  fi
  CLEANUP_IN_PROGRESS=1

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "Shutting down gracefully..."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  # Step 1: Send SIGTERM (graceful shutdown)
  if [[ -n "$WATCH_LOOP_PID" ]] && kill -0 "$WATCH_LOOP_PID" 2>/dev/null; then
    echo "  → Stopping watch loop (PID: $WATCH_LOOP_PID)..."
    kill -TERM "$WATCH_LOOP_PID" 2>/dev/null || true
  fi

  if [[ -n "$VITE_PID" ]] && kill -0 "$VITE_PID" 2>/dev/null; then
    echo "  → Stopping frontend (PID: $VITE_PID)..."
    kill -TERM "$VITE_PID" 2>/dev/null || true
  fi

  if [[ -n "$UVICORN_PID" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo "  → Stopping backend (PID: $UVICORN_PID)..."
    kill -TERM "$UVICORN_PID" 2>/dev/null || true
  fi

  # Step 2: Wait up to 3 seconds for graceful shutdown
  local wait_count=0
  while [[ $wait_count -lt 30 ]]; do
    if [[ -z "$WATCH_LOOP_PID" ]] || ! kill -0 "$WATCH_LOOP_PID" 2>/dev/null; then
      if [[ -z "$VITE_PID" ]] || ! kill -0 "$VITE_PID" 2>/dev/null; then
        if [[ -z "$UVICORN_PID" ]] || ! kill -0 "$UVICORN_PID" 2>/dev/null; then
          echo "✓ All processes stopped gracefully"
          return
        fi
      fi
    fi
    sleep 0.1
    wait_count=$((wait_count + 1))
  done

  # Step 3: Force kill if still running (after 3 seconds)
  echo "  → Forcing shutdown..."
  if [[ -n "$WATCH_LOOP_PID" ]] && kill -0 "$WATCH_LOOP_PID" 2>/dev/null; then
    echo "  ⚠ Force killing watch loop (PID: $WATCH_LOOP_PID)"
    kill -KILL "$WATCH_LOOP_PID" 2>/dev/null || true
  fi

  if [[ -n "$VITE_PID" ]] && kill -0 "$VITE_PID" 2>/dev/null; then
    echo "  ⚠ Force killing frontend (PID: $VITE_PID)"
    kill -KILL "$VITE_PID" 2>/dev/null || true
  fi

  if [[ -n "$UVICORN_PID" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo "  ⚠ Force killing backend (PID: $UVICORN_PID)"
    kill -KILL "$UVICORN_PID" 2>/dev/null || true
  fi

  # Step 4: Clean up any orphaned node processes on port 5173
  if lsof -ti:5173 >/dev/null 2>&1; then
    echo "  ⚠ Cleaning up orphaned port 5173 process..."
    kill -KILL $(lsof -ti:5173) 2>/dev/null || true
  fi

  echo "✓ Shutdown complete"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

trap cleanup EXIT INT TERM

# Wait for all processes (will exit via trap on signal)
wait $WATCH_LOOP_PID $VITE_PID $UVICORN_PID 2>/dev/null || true
