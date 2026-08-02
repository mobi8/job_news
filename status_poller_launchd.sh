#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.jobwatch.telegram-poller"
DOMAIN="gui/$(id -u)"
PLIST_DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
POLLER_SCRIPT="${WORKDIR}/src/api/telegram_poller.py"

echo "Service: ${LABEL}"
echo "Plist: ${PLIST_DEST}"

if launchctl print "${DOMAIN}/${LABEL}" >/tmp/jobwatch_launchd_status.txt 2>/dev/null; then
  echo "launchd: loaded"
  awk '
    /^[[:space:]]*state = / { print "state: " $3 }
    /^[[:space:]]*pid = / { print "pid: " $3 }
    /^[[:space:]]*last exit code = / { print "last exit code: " $5 }
  ' /tmp/jobwatch_launchd_status.txt
else
  echo "launchd: not loaded"
fi

pids=()
while IFS= read -r pid; do
  [[ -n "${pid}" ]] && pids+=("${pid}")
done < <(pgrep -f "${POLLER_SCRIPT}" 2>/dev/null || true)
if [[ ${#pids[@]} -eq 0 ]]; then
  echo "process: not running"
  exit 0
fi

echo "process: running"
for pid in "${pids[@]}"; do
  echo "pid: ${pid}"
  ps -p "${pid}" -o pid= -o command= || true
done
