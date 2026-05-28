#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${WORKDIR}/venv/bin/python3}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

cd "${WORKDIR}"
if [[ -f "${WORKDIR}/.env" ]]; then
  echo "Loading .env..."
  set -a
  # shellcheck disable=SC1091
  source "${WORKDIR}/.env"
  set +a
fi

export PYTHONPATH="${WORKDIR}/src:${PYTHONPATH:-}"

# Check if telegram_poller is already running
if POLLER_PID=$(pgrep -f "src/api/telegram_poller.py"); then
  echo "✓ Telegram poller is already running"
  echo "  PID: $POLLER_PID"
  echo ""
  echo "Check logs with:"
  echo "  tail -f /tmp/telegram_poller.log"
  exit 0
fi

echo "Starting Telegram poller..."
env PYTHONUNBUFFERED=1 "${PYTHON_BIN}" src/api/telegram_poller.py > /tmp/telegram_poller.log 2>&1 &
POLLER_PID=$!

sleep 0.5

# Verify it started successfully
if kill -0 "$POLLER_PID" 2>/dev/null; then
  echo "✓ Telegram poller started successfully"
  echo "  PID: $POLLER_PID"
  echo ""
  echo "Check logs with:"
  echo "  tail -f /tmp/telegram_poller.log"
else
  echo "❌ Failed to start Telegram poller"
  echo "See logs for details:"
  echo "  cat /tmp/telegram_poller.log"
  exit 1
fi
