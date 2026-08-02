#!/usr/bin/env bash
set -euo pipefail

LABEL="com.jobwatch.telegram-poller"
DOMAIN="gui/$(id -u)"
PLIST_DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

echo "Uninstalling ${LABEL}"
launchctl bootout "${DOMAIN}" "${PLIST_DEST}" >/dev/null 2>&1 || launchctl unload "${PLIST_DEST}" >/dev/null 2>&1 || true
rm -f "${PLIST_DEST}"
echo "Removed ${PLIST_DEST}"
