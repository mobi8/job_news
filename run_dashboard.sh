#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${WORKDIR}/frontend"
SKIP_SCRAPE="${NO_SCRAPE:-0}"
JOBS_DIR="${WORKDIR}/outputs"
VENV_DIR="${WORKDIR}/venv"
VENV_PYTHON_VERSION_FILE="${VENV_DIR}/.python-version"
PYTHON_BIN="${PYTHON_BIN:-}"

UVICORN_PID=""
VITE_PID=""
WATCH_LOOP_PID=""
WATCH_LOOP_LOG_TAIL_PID=""
TELEGRAM_POLLER_PID=""
TELEGRAM_SCRAPER_PID=""
CLEANUP_IN_PROGRESS=0

startup_cleanup() {
  for pid in "$TELEGRAM_POLLER_PID" "$WATCH_LOOP_PID" "$WATCH_LOOP_LOG_TAIL_PID" "$VITE_PID" "$UVICORN_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done

  for port in 8000 4173 5173; do
    if lsof -ti:"$port" >/dev/null 2>&1; then
      kill -TERM $(lsof -ti:"$port") 2>/dev/null || true
    fi
  done
}

trap startup_cleanup EXIT INT TERM

select_python() {
  if [[ -n "${PYTHON_BIN}" ]]; then
    if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      echo "  ✖ PYTHON_BIN not found: ${PYTHON_BIN}"
      exit 1
    fi
    return 0
  fi

  for candidate in python3.12 python3.11 python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      return 0
    fi
  done

  echo "  ✖ No usable python3 found"
  exit 1
}

select_python
SELECTED_PYTHON_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "Using Python ${SELECTED_PYTHON_VERSION}: ${PYTHON_BIN}"

# Setup venv with corruption detection
venv_needs_rebuild=0
if [[ ! -d "${VENV_DIR}" ]]; then
  venv_needs_rebuild=1
else
  if [[ -f "${VENV_PYTHON_VERSION_FILE}" ]]; then
    existing_python_version="$(cat "${VENV_PYTHON_VERSION_FILE}")"
  else
    shopt -s nullglob
    existing_python_dirs=("${VENV_DIR}"/lib/python3.*)
    shopt -u nullglob
    existing_python_version="$(basename "${existing_python_dirs[0]:-unknown}" | sed 's/^python//')"
  fi
  if [[ "${existing_python_version}" != "${SELECTED_PYTHON_VERSION}" ]]; then
    echo "  ⚠ venv uses Python ${existing_python_version}; rebuilding with ${SELECTED_PYTHON_VERSION}..."
    rm -rf "${VENV_DIR}"
    venv_needs_rebuild=1
  fi

  # Test if venv is structurally valid without importing Python modules during boot.
  if [[ $venv_needs_rebuild -eq 0 ]] && [[ ! -x "${VENV_DIR}/bin/python3" ]]; then
    echo "  ⚠ venv is corrupted (python broken), rebuilding..."
    rm -rf "${VENV_DIR}"
    venv_needs_rebuild=1
  fi
fi

if [[ $venv_needs_rebuild -eq 1 ]]; then
  echo "Creating Python virtual environment..."
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  echo "${SELECTED_PYTHON_VERSION}" > "${VENV_PYTHON_VERSION_FILE}"
fi

# Activate venv
source "${VENV_DIR}/bin/activate"

install_requirements() {
  local site_packages
  shopt -s nullglob
  local site_package_dirs=("${VENV_DIR}"/lib/python*/site-packages)
  shopt -u nullglob
  site_packages="${site_package_dirs[0]:-}"
  if [[ -n "${site_packages}" \
    && -f "${site_packages}/bs4/__init__.py" \
    && -f "${site_packages}/fastapi/__init__.py" \
    && -f "${site_packages}/requests/__init__.py" \
    && -f "${site_packages}/urllib3/exceptions.py" \
    && -f "${site_packages}/certifi/__init__.py" \
    && -f "${site_packages}/charset_normalizer/__init__.py" \
    && -f "${site_packages}/idna/__init__.py" \
    && -f "${site_packages}/uvicorn/__init__.py" ]]; then
    echo "Dependencies already available ✓"
    return 0
  fi
  echo "Ensuring dependencies are installed..."
  python -m pip install -q \
    "fastapi>=0.115.0" \
    "jinja2>=3.0" \
    "uvicorn>=0.24.0" \
    "requests>=2.31.0" \
    "beautifulsoup4>=4.12.0"
}

rebuild_venv() {
  echo "  ⚠ rebuilding Python virtual environment..."
  rm -rf "${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  echo "${SELECTED_PYTHON_VERSION}" > "${VENV_PYTHON_VERSION_FILE}"
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

# Clean up any older dashboard/watch processes before starting fresh.
kill_matching_processes "telegram poller" "src/api/telegram_poller.py"
kill_matching_processes "telegram poller wrapper" "python3 src/api/telegram_poller.py"
kill_matching_processes "telegram scraper" "src/services/telegram_scraper.py"
kill_matching_processes "watch loop" "src/watch/loop.py"
kill_matching_processes "watch loop wrapper" "caffeinate -s python3 src/watch/loop.py"
kill_matching_processes "scraper" "src/watch/scraper.py"
kill_matching_processes "browser probe" "browser_probe.js"
kill_matching_processes "playwright chrome profile" "chrome-profile-"
kill_matching_processes "backend" "uvicorn src.api.app:app"
kill_matching_processes "frontend" "frontend/.bin/vite"
kill_matching_processes "frontend wrapper" "node_modules/.bin/vite"

if lsof -ti:8000 >/dev/null 2>&1; then
  terminate_pids "port 8000 listener" $(lsof -ti:8000)
fi
if lsof -ti:4173 >/dev/null 2>&1; then
  terminate_pids "port 4173 listener" $(lsof -ti:4173)
fi
if lsof -ti:5173 >/dev/null 2>&1; then
  terminate_pids "port 5173 listener" $(lsof -ti:5173)
fi
sleep 1

# Frontend cleanup & rebuild
cd "${FRONTEND_DIR}"
if [[ ! -d node_modules ]]; then
  echo "  Installing dependencies..."
  npm install --silent 2>/dev/null
fi

# Create job_statuses.json if missing
if [[ ! -f "${JOBS_DIR}/job_statuses.json" ]]; then
  echo '{"statuses": {}}' > "${JOBS_DIR}/job_statuses.json"
fi

cd "${WORKDIR}"
BACKEND_LOG="/tmp/job_watch_backend.log"
: > "${BACKEND_LOG}"
python src/api/simple_server.py > "${BACKEND_LOG}" 2>&1 &
UVICORN_PID=$!
echo "  Backend started (PID: $UVICORN_PID)"

echo "  Waiting for backend API..."
backend_ready=0
for attempt in {1..240}; do
  if curl -fsS --max-time 1 http://127.0.0.1:8000/api/healthz >/dev/null 2>&1; then
    backend_ready=1
    break
  fi
  if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo "  ✖ Backend exited before it was ready"
    tail -n 80 "${BACKEND_LOG}" || true
    exit 1
  fi
  if (( attempt % 20 == 0 )); then
    echo "  Still waiting for backend API... ($((attempt / 2))s)"
  fi
  sleep 0.5
done

if [[ $backend_ready -ne 1 ]]; then
  echo "  ✖ Backend did not become ready on http://127.0.0.1:8000"
  tail -n 80 "${BACKEND_LOG}" || true
  exit 1
fi
echo "  Backend API ready ✓"

cd "${FRONTEND_DIR}"
FRONTEND_LOG="/tmp/job_watch_frontend.log"
FRONTEND_BUILD_LOG="/tmp/job_watch_frontend_build.log"
: > "${FRONTEND_LOG}"
mkdir -p dist/assets

frontend_needs_build=0
if [[ ! -f dist/assets/app.js || ! -f dist/assets/app.css || ! -f dist/index.html ]]; then
  frontend_needs_build=1
elif find src index.html package.json tsconfig.json tsconfig.node.json -type f -newer dist/assets/app.js 2>/dev/null | grep -q .; then
  frontend_needs_build=1
fi

if [[ $frontend_needs_build -eq 1 ]]; then
  echo "  Building frontend bundle..."
  : > "${FRONTEND_BUILD_LOG}"
  if ! ./node_modules/.bin/esbuild src/main.tsx --bundle --format=esm --outfile=dist/assets/app.js --loader:.tsx=tsx --loader:.ts=ts --jsx=automatic > "${FRONTEND_BUILD_LOG}" 2>&1; then
    echo "  ✖ Frontend build failed"
    tail -n 80 "${FRONTEND_BUILD_LOG}" || true
    exit 1
  fi
  cat > dist/index.html <<EOF
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Job Watch Dashboard</title>
    <script type="module" crossorigin src="/assets/app.js"></script>
    <link rel="stylesheet" crossorigin href="/assets/app.css" />
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
EOF
else
  echo "  Frontend bundle is current ✓"
fi

python "${WORKDIR}/src/api/static_frontend_server.py" --dist "${FRONTEND_DIR}/dist" --port 4173 > "${FRONTEND_LOG}" 2>&1 &
VITE_PID=$!
echo "  Frontend started (PID: $VITE_PID)"

# Wait for the static frontend server before opening the browser.
VITE_PORT=4173
frontend_ready=0
echo "  Waiting for frontend..."
for attempt in {1..240}; do
  if grep -qE 'Dashboard frontend running on http://127\.0\.0\.1:[0-9]+/' "${FRONTEND_LOG}"; then
    frontend_ready=1
    break
  fi

  if ! kill -0 "$VITE_PID" 2>/dev/null; then
    echo "  ✖ Frontend exited before it was ready"
    tail -n 80 "${FRONTEND_LOG}" || true
    exit 1
  fi

  if (( attempt % 20 == 0 )); then
    echo "  Still waiting for frontend... ($((attempt / 2))s)"
  fi
  sleep 0.5
done

if [[ $frontend_ready -ne 1 ]]; then
  echo "  ✖ Frontend did not become ready on http://127.0.0.1:${VITE_PORT}"
  tail -n 80 "${FRONTEND_LOG}" || true
  exit 1
fi

echo "  Frontend ready ✓"
echo "✓ Dashboard ready at http://localhost:$VITE_PORT/"
open "http://localhost:$VITE_PORT/" 2>/dev/null || xdg-open "http://localhost:$VITE_PORT/" 2>/dev/null || echo "  Please open http://localhost:$VITE_PORT/ in your browser"

if [[ "${SKIP_SCRAPE}" != "1" ]]; then
cd "${WORKDIR}"
python3 src/api/telegram_poller.py > /tmp/telegram_poller.log 2>&1 &
TELEGRAM_POLLER_PID=$!
echo "  Telegram poller started (PID: $TELEGRAM_POLLER_PID)"
sleep 1

# Test Telegram scraper availability without importing packages during boot.
shopt -s nullglob
site_package_dirs=("${VENV_DIR}"/lib/python*/site-packages)
shopt -u nullglob
site_packages="${site_package_dirs[0]:-}"
if [[ -n "${site_packages}" && -f "${site_packages}/requests/__init__.py" && -f "${site_packages}/urllib3/exceptions.py" && -f "${site_packages}/bs4/__init__.py" ]]; then
  echo "  Telegram scraper dependencies available ✓"
else
  echo "  ⚠ Warning: Telegram scraper dependencies not available"
fi

# Start watch loop directly with caffeinate (keep system awake during long runs)
cd "${WORKDIR}"
# Stream the watch loop log back into this terminal so each scraper phase stays visible.
: > /tmp/watch_loop.log
tail -n 0 -f /tmp/watch_loop.log &
WATCH_LOOP_LOG_TAIL_PID=$!
echo "  Watch loop log tail started (PID: $WATCH_LOOP_LOG_TAIL_PID)"

caffeinate -s python3 src/watch/loop.py > /tmp/watch_loop.log 2>&1 &
WATCH_LOOP_PID=$!
echo "  Watch loop started with caffeinate (PID: $WATCH_LOOP_PID)"
else
  echo "  Skipping Telegram poller and watch loop (NO_SCRAPE=1)"
fi

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

  if [[ -n "$WATCH_LOOP_LOG_TAIL_PID" ]] && kill -0 "$WATCH_LOOP_LOG_TAIL_PID" 2>/dev/null; then
    echo "  → Stopping watch loop log tail (PID: $WATCH_LOOP_LOG_TAIL_PID)..."
    kill -TERM "$WATCH_LOOP_LOG_TAIL_PID" 2>/dev/null || true
  fi

  if [[ -n "$VITE_PID" ]] && kill -0 "$VITE_PID" 2>/dev/null; then
    echo "  → Stopping frontend (PID: $VITE_PID)..."
    kill -TERM "$VITE_PID" 2>/dev/null || true
  fi

  if [[ -n "$UVICORN_PID" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo "  → Stopping backend (PID: $UVICORN_PID)..."
    kill -TERM "$UVICORN_PID" 2>/dev/null || true
  fi

  # Step 2: Wait up to 10 seconds for graceful shutdown
  local wait_count=0
  while [[ $wait_count -lt 100 ]]; do
    local all_stopped=1
    for pid in "$TELEGRAM_POLLER_PID" "$WATCH_LOOP_PID" "$WATCH_LOOP_LOG_TAIL_PID" "$VITE_PID" "$UVICORN_PID"; do
      if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        all_stopped=0
        break
      fi
    done

    if [[ $all_stopped -eq 1 ]]; then
      echo "✓ All processes stopped gracefully"
      return
    fi
    sleep 0.1
    wait_count=$((wait_count + 1))
  done

  # Step 3: Force kill if still running (after 10 seconds)
  echo "  → Forcing shutdown..."
  if [[ -n "$TELEGRAM_POLLER_PID" ]] && kill -0 "$TELEGRAM_POLLER_PID" 2>/dev/null; then
    echo "  ⚠ Force killing Telegram poller (PID: $TELEGRAM_POLLER_PID)"
    kill -KILL "$TELEGRAM_POLLER_PID" 2>/dev/null || true
  fi

  if [[ -n "$WATCH_LOOP_PID" ]] && kill -0 "$WATCH_LOOP_PID" 2>/dev/null; then
    echo "  ⚠ Force killing watch loop (PID: $WATCH_LOOP_PID)"
    kill -KILL "$WATCH_LOOP_PID" 2>/dev/null || true
  fi

  if [[ -n "$WATCH_LOOP_LOG_TAIL_PID" ]] && kill -0 "$WATCH_LOOP_LOG_TAIL_PID" 2>/dev/null; then
    echo "  ⚠ Force killing watch loop log tail (PID: $WATCH_LOOP_LOG_TAIL_PID)"
    kill -KILL "$WATCH_LOOP_LOG_TAIL_PID" 2>/dev/null || true
  fi

  if [[ -n "$VITE_PID" ]] && kill -0 "$VITE_PID" 2>/dev/null; then
    echo "  ⚠ Force killing frontend (PID: $VITE_PID)"
    kill -KILL "$VITE_PID" 2>/dev/null || true
  fi

  if [[ -n "$UVICORN_PID" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo "  ⚠ Force killing backend (PID: $UVICORN_PID)"
    kill -KILL "$UVICORN_PID" 2>/dev/null || true
  fi

  # Step 4: Clean up any orphaned frontend processes on Vite ports.
  for port in 4173 5173; do
    if lsof -ti:"$port" >/dev/null 2>&1; then
      echo "  ⚠ Cleaning up orphaned port ${port} process..."
      kill -KILL $(lsof -ti:"$port") 2>/dev/null || true
    fi
  done

  echo "✓ Shutdown complete"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

trap cleanup EXIT INT TERM

# Wait for all processes (will exit via trap on signal)
WAIT_PIDS=()
[[ -n "$TELEGRAM_POLLER_PID" ]] && WAIT_PIDS+=("$TELEGRAM_POLLER_PID")
[[ -n "$WATCH_LOOP_PID" ]] && WAIT_PIDS+=("$WATCH_LOOP_PID")
[[ -n "$VITE_PID" ]] && WAIT_PIDS+=("$VITE_PID")
[[ -n "$UVICORN_PID" ]] && WAIT_PIDS+=("$UVICORN_PID")
wait "${WAIT_PIDS[@]}" 2>/dev/null || true
