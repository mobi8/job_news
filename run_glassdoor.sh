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

JOB_WATCH_SOURCES="${JOB_WATCH_SOURCES:-glassdoor_uae}"
export JOB_WATCH_SOURCES
export BROWSER_BATCH_WORKERS="${BROWSER_BATCH_WORKERS:-1}"
export BROWSER_GLASSDOOR_BATCH_SIZE="${BROWSER_GLASSDOOR_BATCH_SIZE:-1}"
export BROWSER_GLASSDOOR_BATCH_WORKERS="${BROWSER_GLASSDOOR_BATCH_WORKERS:-1}"
export BROWSER_PROBE_HEARTBEAT_SECONDS="${BROWSER_PROBE_HEARTBEAT_SECONDS:-10}"
export SKIP_LINKEDIN_BROWSER="${SKIP_LINKEDIN_BROWSER:-1}"
export SKIP_INDEED_BROWSER="${SKIP_INDEED_BROWSER:-1}"
export SKIP_JOBSPY="${SKIP_JOBSPY:-1}"

if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -s env \
    JOB_WATCH_SOURCES="${JOB_WATCH_SOURCES}" \
    SKIP_NEWS="1" \
    SKIP_LINKEDIN_BROWSER="${SKIP_LINKEDIN_BROWSER}" \
    SKIP_INDEED_BROWSER="${SKIP_INDEED_BROWSER}" \
    SKIP_JOBSPY="${SKIP_JOBSPY}" \
    GLASSDOOR_ONLY="1" \
    BROWSER_BATCH_WORKERS="${BROWSER_BATCH_WORKERS}" \
    BROWSER_GLASSDOOR_BATCH_SIZE="${BROWSER_GLASSDOOR_BATCH_SIZE}" \
    BROWSER_GLASSDOOR_BATCH_WORKERS="${BROWSER_GLASSDOOR_BATCH_WORKERS}" \
    BROWSER_PROBE_HEARTBEAT_SECONDS="${BROWSER_PROBE_HEARTBEAT_SECONDS}" \
    COLLECTION_TARGET_FILTER_JSON="${COLLECTION_TARGET_FILTER_JSON:-}" \
    "${PYTHON_BIN}" src/watch/glassdoor_batch.py
fi

exec env \
  JOB_WATCH_SOURCES="${JOB_WATCH_SOURCES}" \
  SKIP_NEWS="1" \
  SKIP_LINKEDIN_BROWSER="${SKIP_LINKEDIN_BROWSER}" \
  SKIP_INDEED_BROWSER="${SKIP_INDEED_BROWSER}" \
  SKIP_JOBSPY="${SKIP_JOBSPY}" \
  GLASSDOOR_ONLY="1" \
  BROWSER_BATCH_WORKERS="${BROWSER_BATCH_WORKERS}" \
  BROWSER_GLASSDOOR_BATCH_SIZE="${BROWSER_GLASSDOOR_BATCH_SIZE}" \
  BROWSER_GLASSDOOR_BATCH_WORKERS="${BROWSER_GLASSDOOR_BATCH_WORKERS}" \
  BROWSER_PROBE_HEARTBEAT_SECONDS="${BROWSER_PROBE_HEARTBEAT_SECONDS}" \
  COLLECTION_TARGET_FILTER_JSON="${COLLECTION_TARGET_FILTER_JSON:-}" \
  "${PYTHON_BIN}" src/watch/glassdoor_batch.py
