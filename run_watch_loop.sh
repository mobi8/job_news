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
