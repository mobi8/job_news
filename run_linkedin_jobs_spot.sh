#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${WORKDIR}/venv/bin/python3}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

cd "${WORKDIR}"
if [[ -f "${WORKDIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${WORKDIR}/.env"
  set +a
fi

export PYTHONPATH="${WORKDIR}/src:${PYTHONPATH:-}"
export BROWSER_HEADLESS="${BROWSER_HEADLESS:-1}"
export WS_NO_BUFFER_UTIL="${WS_NO_BUFFER_UTIL:-1}"
export WS_NO_UTF_8_VALIDATE="${WS_NO_UTF_8_VALIDATE:-1}"

exec "${PYTHON_BIN}" src/watch/linkedin_jobs_spot.py "$@"
