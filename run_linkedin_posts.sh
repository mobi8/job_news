#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

select_python_bin() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if [[ -x "${PYTHON_BIN}" ]]; then
      return 0
    fi
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "${PYTHON_BIN}")"
      return 0
    fi
    echo "PYTHON_BIN is set but not executable: ${PYTHON_BIN}" >&2
    exit 1
  fi

  if [[ -x "${WORKDIR}/venv312/bin/python" ]]; then
    PYTHON_BIN="${WORKDIR}/venv312/bin/python"
  elif [[ -x "${WORKDIR}/venv/bin/python" ]]; then
    PYTHON_BIN="${WORKDIR}/venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    echo "No usable Python found. Set PYTHON_BIN explicitly." >&2
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

select_node_bin() {
  if [[ -n "${NODE_BIN:-}" ]]; then
    if [[ -x "${NODE_BIN}" ]]; then
      return 0
    fi
    if command -v "${NODE_BIN}" >/dev/null 2>&1; then
      NODE_BIN="$(command -v "${NODE_BIN}")"
      return 0
    fi
  fi

  if command -v node >/dev/null 2>&1; then
    NODE_BIN="$(command -v node)"
  elif [[ -x "${HOME}/.nvm/versions/node/current/bin/node" ]]; then
    NODE_BIN="${HOME}/.nvm/versions/node/current/bin/node"
  elif [[ -x "/opt/homebrew/bin/node" ]]; then
    NODE_BIN="/opt/homebrew/bin/node"
  elif [[ -x "/usr/local/bin/node" ]]; then
    NODE_BIN="/usr/local/bin/node"
  else
    echo "Node executable not found. Please set NODE_BIN or install Node.js." >&2
    exit 1
  fi
}

select_python_bin

cd "${WORKDIR}"
if [[ -f "${WORKDIR}/.env" ]]; then
  echo "Loading .env..."
  set -a
  # shellcheck disable=SC1091
  source "${WORKDIR}/.env"
  set +a
  export JOBHUNT_ENV_LOADED=1
fi
select_python_bin
log_python_bin
select_node_bin
export PYTHONPATH="${WORKDIR}/src:${PYTHONPATH:-}"
export NODE_BIN
export JOBHUNT_NODE_BIN="${NODE_BIN}"

if [[ "${1:-}" == "spot" ]]; then
  export LINKEDIN_POST_MAX_PLANS="${LINKEDIN_POST_MAX_PLANS:-8}"
  export LINKEDIN_POST_SCROLL_ROUNDS="${LINKEDIN_POST_SCROLL_ROUNDS:-1}"
  export LINKEDIN_POST_BATCH_SIZE="${LINKEDIN_POST_BATCH_SIZE:-8}"
  export LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS="${LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS:-1}"
  export LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS="${LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS:-2}"
  export LINKEDIN_POST_QUERY_PAUSE_MIN_SECONDS="${LINKEDIN_POST_QUERY_PAUSE_MIN_SECONDS:-2}"
  export LINKEDIN_POST_QUERY_PAUSE_MAX_SECONDS="${LINKEDIN_POST_QUERY_PAUSE_MAX_SECONDS:-4}"
fi

# Optional positional args to avoid shell env-var mistakes:
#   ./run_linkedin_posts.sh 36 48   # run plans 36..48
if [[ "${1:-}" != "spot" && "${1:-}" =~ ^[0-9]+$ ]]; then
  export LINKEDIN_POST_START_PLAN="$1"
fi
if [[ "${1:-}" != "spot" && "${2:-}" =~ ^[0-9]+$ ]]; then
  export LINKEDIN_POST_MAX_PLANS="$2"
fi
export LINKEDIN_POSTS_PROFILE_DIR="${LINKEDIN_POSTS_PROFILE_DIR:-${WORKDIR}/outputs/linkedin-post-profile}"
export LINKEDIN_POST_MAX_PLANS="${LINKEDIN_POST_MAX_PLANS:-96}"
export LINKEDIN_POST_SCROLL_ROUNDS="${LINKEDIN_POST_SCROLL_ROUNDS:-2}"
# Stability controls: run searches in small sequential batches, then cool down.
export LINKEDIN_POST_BATCH_SIZE="${LINKEDIN_POST_BATCH_SIZE:-2}"
export LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS="${LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS:-25}"
export LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS="${LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS:-45}"
export LINKEDIN_POST_QUERY_PAUSE_MIN_SECONDS="${LINKEDIN_POST_QUERY_PAUSE_MIN_SECONDS:-4}"
export LINKEDIN_POST_QUERY_PAUSE_MAX_SECONDS="${LINKEDIN_POST_QUERY_PAUSE_MAX_SECONDS:-6}"
# Default to background/headless scraping with the existing persistent profile.
# If the session is expired, exit quickly and ask for manual login.
export LINKEDIN_POST_HEADLESS="${LINKEDIN_POST_HEADLESS:-1}"
export LINKEDIN_POST_AUTO_LOGIN_SETUP="${LINKEDIN_POST_AUTO_LOGIN_SETUP:-0}"
export LINKEDIN_USE_SYSTEM_CHROME="${LINKEDIN_USE_SYSTEM_CHROME:-1}"
export LINKEDIN_CDP_PORT="${LINKEDIN_CDP_PORT:-9223}"
export BROWSER_PROBE_HEARTBEAT_SECONDS="${BROWSER_PROBE_HEARTBEAT_SECONDS:-10}"
export LINKEDIN_POST_TOTAL_TIMEOUT_SECONDS="${LINKEDIN_POST_TOTAL_TIMEOUT_SECONDS:-5400}"
# Each Python-managed batch disconnects/restarts the scraper Chrome profile.
# Keep Chrome open by default; only close it when explicitly requested.
export LINKEDIN_CLOSE_CHROME_AFTER="${LINKEDIN_CLOSE_CHROME_AFTER:-0}"

if [[ "${LINKEDIN_POST_ONCE:-0}" == "1" ]]; then
  export LINKEDIN_POST_START_PLAN=1
  export LINKEDIN_POST_MAX_PLANS=1
  export LINKEDIN_POST_BATCH_SIZE=1
  export LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS=0
  export LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS=0
  export LINKEDIN_POST_QUERY_PAUSE_MIN_SECONDS=0
  export LINKEDIN_POST_QUERY_PAUSE_MAX_SECONDS=0
  export LINKEDIN_CLOSE_CHROME_AFTER=1
  echo "[linkedin-posts] one-shot mode enabled: max_plans=1 batch_size=1 close_chrome=1"
fi

mkdir -p "${LINKEDIN_POSTS_PROFILE_DIR}"
LOCK_PATH="${WORKDIR}/outputs/linkedin_posts.lock"

if [[ -f "${LOCK_PATH}" ]]; then
  lock_info="$("${PYTHON_BIN}" -c 'import json, sys; data=json.load(open(sys.argv[1])); print("{} {}".format(int(data.get("pid") or 0), data.get("started_at_epoch") or ""))' "${LOCK_PATH}" 2>/dev/null || true)"
  lock_pid="${lock_info%% *}"
  lock_started="${lock_info#* }"
  if [[ "${lock_pid}" =~ ^[0-9]+$ ]] && kill -0 "${lock_pid}" 2>/dev/null; then
    runtime="$("${PYTHON_BIN}" -c 'import sys, time; started=float(sys.argv[1] or 0); elapsed=max(0, int(time.time()-started)); h, r=divmod(elapsed, 3600); m, s=divmod(r, 60); print(f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s"))' "${lock_started}" 2>/dev/null || echo "unknown")"
    echo "LinkedIn posts already running: PID=${lock_pid}, runtime=${runtime}"
    exit 75
  fi
  echo "Removing stale LinkedIn posts lock: ${LOCK_PATH}"
  rm -f "${LOCK_PATH}"
fi

# Cleanup function for EXIT/INT/TERM
cleanup_processes() {
  echo "Cleaning up LinkedIn posts runner..."
  pkill -f "linkedin_posts_probe" 2>/dev/null || true
  sleep 0.5
}

trap cleanup_processes EXIT INT TERM

if ! lsof -ti:"${LINKEDIN_CDP_PORT}" >/dev/null 2>&1; then
  echo "  ⚠ LinkedIn Chrome CDP port ${LINKEDIN_CDP_PORT} is not listening."
  echo "  → If this is the first run, use ./setup_linkedin_posts_login.sh and log in once."
fi

# Kill stale processes before starting
echo "Clearing stale LinkedIn posts processes..."
pkill -f "linkedin_posts_probe" 2>/dev/null || true
sleep 1

# Chrome must be launched with --remote-debugging-port for the scraper to attach.
# The Node probe attaches to a healthy LinkedIn profile Chrome when possible and
# only restarts the dedicated profile when CDP is missing or unusable.

if command -v caffeinate >/dev/null 2>&1; then
  echo "Starting LinkedIn posts runner..."
  env PYTHONUNBUFFERED=1 "${PYTHON_BIN}" src/watch/linkedin_posts.py "$@" &
else
  echo "Starting LinkedIn posts runner..."
  env PYTHONUNBUFFERED=1 "${PYTHON_BIN}" src/watch/linkedin_posts.py "$@" &
fi
runner_pid="$!"
started_at="$(date +%s)"
while kill -0 "${runner_pid}" 2>/dev/null; do
  now="$(date +%s)"
  if (( now - started_at >= LINKEDIN_POST_TOTAL_TIMEOUT_SECONDS )); then
    echo "LinkedIn posts runner shell timeout after ${LINKEDIN_POST_TOTAL_TIMEOUT_SECONDS}s"
    kill "${runner_pid}" 2>/dev/null || true
    sleep 2
    kill -9 "${runner_pid}" 2>/dev/null || true
    wait "${runner_pid}" 2>/dev/null || true
    exit 124
  fi
  sleep 2
done
wait "${runner_pid}"
