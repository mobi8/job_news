#!/usr/bin/env bash
# Detached poller restart helper
# Called after update success message is sent to Telegram
# Runs in background to avoid blocking Telegram response

set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="/tmp/jobwatch_update_restart.log"
ERROR_FILE="/tmp/jobwatch_update_restart.error.log"

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting detached poller restart..."

  # Wait before restarting to ensure Telegram response is sent
  sleep 2

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Uninstalling current poller..."
  if ! "$WORKDIR/uninstall_poller_launchd.sh" >> "$LOG_FILE" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] uninstall failed (exit code $?)" >> "$ERROR_FILE"
  fi

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Installing new poller..."
  if ! "$WORKDIR/install_poller_launchd.sh" >> "$LOG_FILE" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] install failed (exit code $?)" >> "$ERROR_FILE"
  fi

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Poller restart complete"
} >> "$LOG_FILE" 2>&1
