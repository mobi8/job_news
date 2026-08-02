#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.jobwatch.telegram-poller"
DOMAIN="gui/$(id -u)"
PLIST_TEMPLATE="${WORKDIR}/config/launchd/${LABEL}.plist.template"
PLIST_DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
PYTHON_BIN="${WORKDIR}/venv312/bin/python"
POLLER_SCRIPT="${WORKDIR}/src/api/telegram_poller.py"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing Python runtime: ${PYTHON_BIN}" >&2
  exit 1
fi

if [[ ! -f "${PLIST_TEMPLATE}" ]]; then
  echo "Missing plist template: ${PLIST_TEMPLATE}" >&2
  exit 1
fi

echo "Installing ${LABEL}"
echo "  Python: ${PYTHON_BIN}"
echo "  Script: ${POLLER_SCRIPT}"

mkdir -p "${HOME}/Library/LaunchAgents"
cp "${PLIST_TEMPLATE}" "${PLIST_DEST}"
plutil -lint "${PLIST_DEST}"

echo "Stopping existing launchd service if present..."
launchctl bootout "${DOMAIN}" "${PLIST_DEST}" >/dev/null 2>&1 || launchctl unload "${PLIST_DEST}" >/dev/null 2>&1 || true

echo "Stopping standalone poller processes if present..."
while IFS= read -r pid; do
  [[ -n "${pid}" ]] || continue
  echo "  Stopping PID ${pid}"
  kill -TERM "${pid}" 2>/dev/null || true
done < <(pgrep -f "${POLLER_SCRIPT}" 2>/dev/null || true)
sleep 1

echo "Starting launchd service..."
if ! launchctl bootstrap "${DOMAIN}" "${PLIST_DEST}" 2>/tmp/jobwatch_launchd_bootstrap.err; then
  echo "  bootstrap failed; trying legacy launchctl load..."
  cat /tmp/jobwatch_launchd_bootstrap.err >&2 || true
  launchctl load "${PLIST_DEST}"
fi

launchctl kickstart -k "${DOMAIN}/${LABEL}" >/dev/null 2>&1 || true
sleep 2

"${WORKDIR}/status_poller_launchd.sh"
