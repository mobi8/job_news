#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${WORKDIR}/frontend"
START_WORKERS=0
JOBS_DIR="${WORKDIR}/outputs"
PYTHON_BIN="${PYTHON_BIN:-}"

UVICORN_PID=""
VITE_PID=""
TELEGRAM_SCRAPER_PID=""
CLEANUP_IN_PROGRESS=0

export WS_NO_BUFFER_UTIL="${WS_NO_BUFFER_UTIL:-1}"
export WS_NO_UTF_8_VALIDATE="${WS_NO_UTF_8_VALIDATE:-1}"

case "${1:-}" in
  --with-workers|--full)
    START_WORKERS=0
    echo "Worker startup is disabled. Dashboard starts API, frontend, and browser only."
    shift
    ;;
  --ui-only|--no-workers)
    START_WORKERS=0
    shift
    ;;
  --help|-h)
    echo "Usage: ./run_dashboard.sh [--ui-only]"
    echo "  --ui-only       Start API, frontend, and browser only."
    echo "  --with-workers  Legacy option; workers remain disabled."
    exit 0
    ;;
esac

startup_cleanup() {
  for pid in "$VITE_PID" "$UVICORN_PID"; do
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
    if [[ -x "${PYTHON_BIN}" ]]; then
      return 0
    fi
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "${PYTHON_BIN}")"
      return 0
    fi
    echo "  ✖ PYTHON_BIN not found or not executable: ${PYTHON_BIN}"
    exit 1
  fi

  if [[ -x "${WORKDIR}/venv312/bin/python" ]]; then
    PYTHON_BIN="${WORKDIR}/venv312/bin/python"
  elif [[ -x "${WORKDIR}/venv/bin/python" ]]; then
    PYTHON_BIN="${WORKDIR}/venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    echo "  ✖ No usable python3 found"
    exit 1
  fi
}

log_python_bin() {
  local version
  version="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
  echo "Using Python: ${PYTHON_BIN} (${version})"
  if "${PYTHON_BIN}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 14) else 1)'; then
    echo "WARNING: Python ${version} may be incompatible with current pinned dependencies; Python 3.12 is the verified runtime."
  fi
}

verify_python_runtime() {
  if ! "${PYTHON_BIN}" -c 'import sys, yaml; print(f"Runtime Python: {sys.executable}"); print(f"PyYAML: {yaml.__version__}")'; then
    echo "  ✖ PyYAML is required. Install dependencies for the selected Python:"
    echo "    ${PYTHON_BIN} -m pip install -r requirements.txt"
    exit 1
  fi
}

install_requirements() {
  if "${PYTHON_BIN}" -c 'import bs4, fastapi, requests, urllib3, certifi, charset_normalizer, idna, uvicorn, yaml' >/dev/null 2>&1; then
    echo "Dependencies already available ✓"
    return 0
  fi

  echo "Ensuring dependencies are installed for ${PYTHON_BIN}..."
  "${PYTHON_BIN}" -m pip install -q -r "${WORKDIR}/requirements.txt"
}

select_python
log_python_bin

if ! install_requirements; then
  echo "  ✖ dependency install failed for selected Python: ${PYTHON_BIN}"
  exit 1
fi
verify_python_runtime

export PYTHONPATH="${WORKDIR}/src:${PYTHONPATH:-}"

echo "Starting Job Watch backend + frontend..."

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

# Clean up only dashboard-owned API/frontend processes before starting fresh.
kill_matching_processes "backend" "src/api/simple_server.py"
kill_matching_processes "backend" "uvicorn src.api.app:app"
kill_matching_processes "frontend" "static_frontend_server.py"
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
"${PYTHON_BIN}" src/api/simple_server.py > "${BACKEND_LOG}" 2>&1 &
UVICORN_PID=$!
echo "  Backend started (PID: $UVICORN_PID)"
echo "  Backend Python: $("${PYTHON_BIN}" -c 'import sys; print(sys.executable)')"

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

"${PYTHON_BIN}" "${WORKDIR}/src/api/static_frontend_server.py" --dist "${FRONTEND_DIR}/dist" --port 4173 > "${FRONTEND_LOG}" 2>&1 &
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

echo "  Dashboard mode: workers are not started."
echo "  Telegram poller is managed by launchd; watch loop is disabled."

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
    for pid in "$VITE_PID" "$UVICORN_PID"; do
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
[[ -n "$VITE_PID" ]] && WAIT_PIDS+=("$VITE_PID")
[[ -n "$UVICORN_PID" ]] && WAIT_PIDS+=("$UVICORN_PID")
wait "${WAIT_PIDS[@]}" 2>/dev/null || true
