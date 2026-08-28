#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.jobwatch.telegram-poller"
DOMAIN="gui/$(id -u)"
PLIST_DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
PYTHON_BIN="${WORKDIR}/venv/bin/python"

usage() {
  cat <<EOF
Usage: ./run_poller.sh [--foreground]

Default:
  Show launchd service status. If the service is installed, this script does
  not start another poller.

Options:
  --foreground   Run telegram_poller.py in the current terminal when launchd is
                 not loaded and no poller is already running.
  --help         Show this help.

Install launchd service:
  ./install_poller_launchd.sh
EOF
}

select_python_bin() {
  if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "Missing project Python runtime: ${PYTHON_BIN}" >&2
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

launchd_loaded() {
  launchctl print "${DOMAIN}/${LABEL}" >/dev/null 2>&1
}

poller_pids() {
  pgrep -f "${WORKDIR}/src/api/telegram_poller.py" 2>/dev/null || true
}

case "${1:-}" in
  --help|-h)
    usage
    exit 0
    ;;
  --foreground|"")
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

cd "${WORKDIR}"
if [[ -f "${WORKDIR}/.env" ]]; then
  echo "Loading .env..."
  set -a
  # shellcheck disable=SC1091
  source "${WORKDIR}/.env"
  set +a
fi

if launchd_loaded; then
  echo "launchd service is installed; not starting a duplicate poller."
  "${WORKDIR}/status_poller_launchd.sh"
  exit 0
fi

existing_pids=()
while IFS= read -r pid; do
  [[ -n "${pid}" ]] && existing_pids+=("${pid}")
done < <(poller_pids)
if [[ ${#existing_pids[@]} -gt 0 ]]; then
  echo "telegram_poller.py is already running; not starting a duplicate."
  printf 'pid: %s\n' "${existing_pids[@]}"
  exit 0
fi

if [[ "${1:-}" != "--foreground" ]]; then
  echo "launchd service is not installed."
  echo "Install it with: ./install_poller_launchd.sh"
  echo "For a temporary terminal-bound run: ./run_poller.sh --foreground"
  exit 0
fi

select_python_bin
log_python_bin
export PYTHONPATH="${WORKDIR}/src:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

echo "Starting Telegram poller in foreground. Press Ctrl-C to stop."
exec "${PYTHON_BIN}" src/api/telegram_poller.py
