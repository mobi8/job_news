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
  set -a
  # shellcheck disable=SC1091
  source "${WORKDIR}/.env"
  set +a
fi
select_python_bin
log_python_bin

export PYTHONPATH="${WORKDIR}/src:${PYTHONPATH:-}"
export JOB_WATCH_SOURCES="${JOB_WATCH_SOURCES:-jobvite_pragmaticplay,smartrecruitment,igamingrecruitment,igaminghunt_bamboohr,jobrapido_uae,jobleads,linkedin_public,linkedin_emea,indeed_uae}"
export SKIP_LINKEDIN_BROWSER="${SKIP_LINKEDIN_BROWSER:-0}"
export SKIP_INDEED_BROWSER="${SKIP_INDEED_BROWSER:-0}"
export SKIP_DRJOBS_BROWSER="${SKIP_DRJOBS_BROWSER:-1}"
export SKIP_GLASSDOOR_BROWSER="${SKIP_GLASSDOOR_BROWSER:-1}"
export SKIP_JOBSPY="${SKIP_JOBSPY:-0}"
export SKIP_LINKEDIN_JOB_SPOT="${SKIP_LINKEDIN_JOB_SPOT:-1}"
export BROWSER_PROBE_HEARTBEAT_SECONDS="${BROWSER_PROBE_HEARTBEAT_SECONDS:-10}"

echo "Starting full watch loop."
echo "  Sources: ${JOB_WATCH_SOURCES}"
echo "  LinkedIn browser: $([[ "${SKIP_LINKEDIN_BROWSER}" == "1" ]] && echo off || echo on)"
echo "  Indeed browser: $([[ "${SKIP_INDEED_BROWSER}" == "1" ]] && echo off || echo on)"
echo "  Indeed JobSpy: $([[ "${SKIP_JOBSPY}" == "1" ]] && echo off || echo on)"
echo "  Telegram channels: $([[ "${SKIP_TELEGRAM_SCRAPER:-0}" == "1" ]] && echo off || echo on)"
echo "  LinkedIn spot: $([[ "${SKIP_LINKEDIN_JOB_SPOT}" == "1" ]] && echo off || echo on)"
echo "  Browser heartbeat: every ${BROWSER_PROBE_HEARTBEAT_SECONDS}s"

if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -s env PYTHONUNBUFFERED=1 "${PYTHON_BIN}" src/watch/loop.py
fi

exec env PYTHONUNBUFFERED=1 "${PYTHON_BIN}" src/watch/loop.py
