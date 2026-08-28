#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${WORKDIR}/venv/bin/python"

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

select_python_bin

cd "${WORKDIR}"
if [[ -f "${WORKDIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${WORKDIR}/.env"
  set +a
fi
select_python_bin
log_python_bin

export PYTHONPATH="${WORKDIR}/src:${PYTHONPATH:-}"
export BROWSER_HEADLESS="${BROWSER_HEADLESS:-1}"
export WS_NO_BUFFER_UTIL="${WS_NO_BUFFER_UTIL:-1}"
export WS_NO_UTF_8_VALIDATE="${WS_NO_UTF_8_VALIDATE:-1}"
export BROWSER_PROBE_HEARTBEAT_SECONDS="${BROWSER_PROBE_HEARTBEAT_SECONDS:-10}"

exec env PYTHONUNBUFFERED=1 "${PYTHON_BIN}" src/watch/linkedin_jobs_spot.py "$@"
