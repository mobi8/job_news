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

select_python_bin

cd "${WORKDIR}"
if [[ -f "${WORKDIR}/.env" ]]; then
  echo "Loading .env..."
  set -a
  # shellcheck disable=SC1091
  source "${WORKDIR}/.env"
  set +a
fi
select_python_bin
log_python_bin

export PYTHONPATH="${WORKDIR}/src:${PYTHONPATH:-}"

# Check if telegram_poller is already running
if OLD_PID=$(pgrep -f "src/api/telegram_poller.py"); then
  echo "Stopping existing poller (PID: $OLD_PID)..."
  kill "$OLD_PID" 2>/dev/null || true
  sleep 1
fi

echo "Starting Telegram poller..."
env PYTHONUNBUFFERED=1 "${PYTHON_BIN}" src/api/telegram_poller.py > /tmp/telegram_poller.log 2>&1 &
POLLER_PID=$!

sleep 0.5

# Verify it started successfully
if kill -0 "$POLLER_PID" 2>/dev/null; then
  echo "✓ Telegram poller started successfully"
  if [[ -n "${OLD_PID:-}" ]]; then
    echo "  Old PID: $OLD_PID → New PID: $POLLER_PID"
  else
    echo "  PID: $POLLER_PID"
  fi
  echo ""
  echo "Check logs with:"
  echo "  tail -f /tmp/telegram_poller.log"
else
  echo "❌ Failed to start Telegram poller"
  echo "See logs for details:"
  echo "  cat /tmp/telegram_poller.log"
  exit 1
fi
