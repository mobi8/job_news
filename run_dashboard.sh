#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${WORKDIR}/frontend"
SKIP_SCRAPE="${NO_SCRAPE:-0}"
JOBS_DIR="${WORKDIR}/outputs"
VENV_DIR="${WORKDIR}/venv"

UVICORN_PID=""
VITE_PID=""
SCRAPER_PID=""
SCRAPER_TAIL_PID=""
WATCH_LOOP_PID=""
TELEGRAM_POLLER_PID=""
TELEGRAM_SCRAPER_PID=""
CLEANUP_IN_PROGRESS=0

# Setup venv with corruption detection
venv_needs_rebuild=0
if [[ ! -d "${VENV_DIR}" ]]; then
  venv_needs_rebuild=1
else
  # Test if venv is valid by checking if pip works
  if ! "${VENV_DIR}/bin/python3" -m pip --version >/dev/null 2>&1; then
    echo "  ⚠ venv is corrupted (pip broken), rebuilding..."
    rm -rf "${VENV_DIR}"
    venv_needs_rebuild=1
  fi
fi

if [[ $venv_needs_rebuild -eq 1 ]]; then
  echo "Creating Python virtual environment..."
  python3 -m venv "${VENV_DIR}"
fi

# Some Python installs ship a venv with a half-broken pip bootstrap. Re-run ensurepip
# so the dashboard can recover without looping on a corrupt pip install.
if ! "${VENV_DIR}/bin/python3" -m ensurepip --upgrade >/dev/null 2>&1; then
  echo "  ⚠ ensurepip bootstrap failed, retrying with a clean venv..."
  rm -rf "${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/python3" -m ensurepip --upgrade >/dev/null 2>&1 || true
fi

"${VENV_DIR}/bin/python3" -m pip install --upgrade --quiet pip setuptools wheel >/dev/null 2>&1 || true

# Activate venv
source "${VENV_DIR}/bin/activate"

install_requirements() {
  echo "Ensuring dependencies are installed..."
  python -m pip install -q -r "${WORKDIR}/requirements.txt"
}

rebuild_venv() {
  echo "  ⚠ rebuilding Python virtual environment..."
  rm -rf "${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/python3" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "${VENV_DIR}/bin/python3" -m pip install --upgrade --quiet pip setuptools wheel >/dev/null 2>&1 || true
  source "${VENV_DIR}/bin/activate"
}

if ! install_requirements; then
  echo "  ⚠ dependency install failed, rebuilding venv and retrying..."
  rebuild_venv
  if ! install_requirements; then
    echo "  ✖ dependency install failed after venv rebuild"
    exit 1
  fi
fi

export PYTHONPATH="${WORKDIR}/src:${PYTHONPATH:-}"

# Keep browser-based scraping conservative during the dashboard run so one slow
# LinkedIn batch does not starve the rest of the pipeline.
export BROWSER_BATCH_WORKERS="${BROWSER_BATCH_WORKERS:-1}"
export BROWSER_LINKEDIN_BATCH_SIZE="${BROWSER_LINKEDIN_BATCH_SIZE:-1}"
export BROWSER_INDEED_BATCH_SIZE="${BROWSER_INDEED_BATCH_SIZE:-1}"
export BROWSER_GLASSDOOR_BATCH_SIZE="${BROWSER_GLASSDOOR_BATCH_SIZE:-1}"
export BROWSER_GLASSDOOR_BATCH_WORKERS=1
# Keep the dashboard bootstrap scrape light. Glassdoor stays on the separate
# batch path so a manual dashboard run does not burn extra Browserless units.
export DASHBOARD_STARTUP_SOURCES="${DASHBOARD_STARTUP_SOURCES:-jobvite_pragmaticplay,smartrecruitment,igamingrecruitment,jobrapido_uae,jobleads,gamblingcareers_remote,himalayas_igaming,linkedin_public,linkedin_georgia,linkedin_malta,indeed_uae,indeed_browserless_uae}"

echo "Starting Job Watch backend + frontend + watch loop..."

terminate_pids() {
  local label="$1"
  shift
  local pids=("$@")
  if [[ ${#pids[@]} -eq 0 ]]; then
    return 0
  fi

  echo "  Stopping ${label}: ${pids[*]}"
  for pid in "${pids[@]}"; do
    kill -TERM "$pid" 2>/dev/null || true
  done

  local wait_count=0
  while [[ $wait_count -lt 30 ]]; do
    local still_running=0
    for pid in "${pids[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        still_running=1
        break
      fi
    done
    if [[ $still_running -eq 0 ]]; then
      return 0
    fi
    sleep 0.1
    wait_count=$((wait_count + 1))
  done

  echo "  Forcing ${label} shutdown..."
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done
}

kill_matching_processes() {
  local label="$1"
  local pattern="$2"
  local pids=()
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && pids+=("$pid")
  done < <(pgrep -f "$pattern" 2>/dev/null || true)
  if [[ ${#pids[@]} -eq 0 ]]; then
    return 0
  fi
  terminate_pids "$label" "${pids[@]}"
}

cleanup_stale_state() {
  echo "  Cleaning up stale watch processes from a previous run..."
  kill_matching_processes "telegram poller" "src/api/telegram_poller.py"
  kill_matching_processes "telegram poller wrapper" "python3 src/api/telegram_poller.py"
  kill_matching_processes "telegram scraper" "src/services/telegram_scraper.py"
  kill_matching_processes "watch loop" "src/watch/loop.py"
  kill_matching_processes "watch loop wrapper" "caffeinate -s python3 src/watch/loop.py"
  kill_matching_processes "scraper" "src/watch/scraper.py"
  kill_matching_processes "scraper collect wrapper" "python3 src/watch/scraper.py collect"
  kill_matching_processes "glassdoor batch" "src/watch/glassdoor_batch.py"
  kill_matching_processes "glassdoor browserless probe" "browserless_glassdoor_probe.js"
  kill_matching_processes "browser probe" "browser_probe.js"
  kill_matching_processes "playwright chrome profile" "chrome-profile-"
  kill_matching_processes "scraper log tail" "job_watch_scraper.log"
  kill_matching_processes "backend" "uvicorn src.api.app:app"
  kill_matching_processes "frontend" "frontend/.bin/vite"
  kill_matching_processes "frontend wrapper" "node_modules/.bin/vite"

  rm -f "${WORKDIR}/outputs/watch_loop.lock" \
        "${WORKDIR}/outputs/scrape_run.lock" \
        "${WORKDIR}/outputs/job_watch_scraper.log"
}

# Clean up any older dashboard/watch processes before starting fresh.
cleanup_stale_state

if lsof -ti:8000 >/dev/null 2>&1; then
  terminate_pids "port 8000 listener" $(lsof -ti:8000)
fi
if lsof -ti:5173 >/dev/null 2>&1; then
  terminate_pids "port 5173 listener" $(lsof -ti:5173)
fi
sleep 1

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
python3 src/api/telegram_poller.py > /tmp/telegram_poller.log 2>&1 &
TELEGRAM_POLLER_PID=$!
echo "  Telegram poller started (PID: $TELEGRAM_POLLER_PID)"
sleep 1

# Test Telegram scraper availability
if python3 -c "import requests; import bs4" 2>/dev/null; then
  echo "  Telegram scraper dependencies available ✓"
else
  echo "  ⚠ Warning: Telegram scraper dependencies not available"
fi

# Start watch loop directly with caffeinate (keep system awake during long runs)
cd "${WORKDIR}"
caffeinate -s python3 src/watch/loop.py > /tmp/watch_loop.log 2>&1 &
WATCH_LOOP_PID=$!
echo "  Watch loop started with caffeinate (PID: $WATCH_LOOP_PID)"

cd "${WORKDIR}"
uvicorn src.api.app:app --log-level info &
UVICORN_PID=$!
echo "  Backend started (PID: $UVICORN_PID)"

cd "${FRONTEND_DIR}"
./node_modules/.bin/vite &
VITE_PID=$!
echo "  Frontend started (PID: $VITE_PID)"

if [[ "${SKIP_SCRAPE}" != "1" ]]; then
  echo "Running scraper (with detailed descriptions) in background..."
  cd "${WORKDIR}"
  touch /tmp/job_watch_scraper.log
  JOB_WATCH_SOURCES="${DASHBOARD_STARTUP_SOURCES}" python3 src/watch/scraper.py collect > /tmp/job_watch_scraper.log 2>&1 &
  SCRAPER_PID=$!
  echo "  Scraper started (PID: $SCRAPER_PID)"
  tail -n +1 -f /tmp/job_watch_scraper.log &
  SCRAPER_TAIL_PID=$!
  echo "  Scraper log tail started (PID: $SCRAPER_TAIL_PID)"
fi

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

echo "✓ Dashboard ready at http://127.0.0.1:$VITE_PORT/"
open "http://127.0.0.1:$VITE_PORT/" 2>/dev/null || xdg-open "http://127.0.0.1:$VITE_PORT/" 2>/dev/null || echo "  Please open http://127.0.0.1:$VITE_PORT/ in your browser"

cleanup() {
  if [[ $CLEANUP_IN_PROGRESS -eq 1 ]]; then
    return
  fi
  CLEANUP_IN_PROGRESS=1

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "Shutting down gracefully..."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  kill_matching_processes "watch loop" "src/watch/loop.py"
  kill_matching_processes "watch loop wrapper" "caffeinate -s python3 src/watch/loop.py"

  # Step 1: Send SIGTERM (graceful shutdown)
  if [[ -n "$TELEGRAM_POLLER_PID" ]] && kill -0 "$TELEGRAM_POLLER_PID" 2>/dev/null; then
    echo "  → Stopping Telegram poller (PID: $TELEGRAM_POLLER_PID)..."
    kill -TERM "$TELEGRAM_POLLER_PID" 2>/dev/null || true
  fi

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

  if [[ -n "$SCRAPER_PID" ]] && kill -0 "$SCRAPER_PID" 2>/dev/null; then
    echo "  → Stopping scraper (PID: $SCRAPER_PID)..."
    kill -TERM "$SCRAPER_PID" 2>/dev/null || true
  fi

  if [[ -n "$SCRAPER_TAIL_PID" ]] && kill -0 "$SCRAPER_TAIL_PID" 2>/dev/null; then
    echo "  → Stopping scraper log tail (PID: $SCRAPER_TAIL_PID)..."
    kill -TERM "$SCRAPER_TAIL_PID" 2>/dev/null || true
  fi

  # Step 2: Wait up to 3 seconds for graceful shutdown
  local wait_count=0
  while [[ $wait_count -lt 30 ]]; do
    local all_stopped=0
    if [[ -z "$TELEGRAM_POLLER_PID" ]] || ! kill -0 "$TELEGRAM_POLLER_PID" 2>/dev/null; then
      if [[ -z "$WATCH_LOOP_PID" ]] || ! kill -0 "$WATCH_LOOP_PID" 2>/dev/null; then
        if [[ -z "$VITE_PID" ]] || ! kill -0 "$VITE_PID" 2>/dev/null; then
          if [[ -z "$UVICORN_PID" ]] || ! kill -0 "$UVICORN_PID" 2>/dev/null; then
            if [[ -z "$SCRAPER_PID" ]] || ! kill -0 "$SCRAPER_PID" 2>/dev/null; then
              if [[ -z "$SCRAPER_TAIL_PID" ]] || ! kill -0 "$SCRAPER_TAIL_PID" 2>/dev/null; then
                all_stopped=1
              fi
            fi
          fi
        fi
      fi
    fi

    if [[ $all_stopped -eq 1 ]]; then
      echo "✓ All processes stopped gracefully"
      return
    fi
    sleep 0.1
    wait_count=$((wait_count + 1))
  done

  # Step 3: Force kill if still running (after 3 seconds)
  echo "  → Forcing shutdown..."
  if [[ -n "$TELEGRAM_POLLER_PID" ]] && kill -0 "$TELEGRAM_POLLER_PID" 2>/dev/null; then
    echo "  ⚠ Force killing Telegram poller (PID: $TELEGRAM_POLLER_PID)"
    kill -KILL "$TELEGRAM_POLLER_PID" 2>/dev/null || true
  fi

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

  if [[ -n "$SCRAPER_PID" ]] && kill -0 "$SCRAPER_PID" 2>/dev/null; then
    echo "  ⚠ Force killing scraper (PID: $SCRAPER_PID)"
    kill -KILL "$SCRAPER_PID" 2>/dev/null || true
  fi

  if [[ -n "$SCRAPER_TAIL_PID" ]] && kill -0 "$SCRAPER_TAIL_PID" 2>/dev/null; then
    echo "  ⚠ Force killing scraper log tail (PID: $SCRAPER_TAIL_PID)"
    kill -KILL "$SCRAPER_TAIL_PID" 2>/dev/null || true
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
wait $TELEGRAM_POLLER_PID $WATCH_LOOP_PID $VITE_PID $UVICORN_PID $SCRAPER_PID $SCRAPER_TAIL_PID 2>/dev/null || true
