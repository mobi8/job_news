#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${WORKDIR}/venv/bin/python3}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

cd "${WORKDIR}"

# Backup external environment variables before sourcing .env
PRESET_BROWSER_BATCH_WORKERS="${BROWSER_BATCH_WORKERS:-}"
PRESET_BROWSER_LINKEDIN_BATCH_SIZE="${BROWSER_LINKEDIN_BATCH_SIZE:-}"
PRESET_BROWSER_INDEED_BATCH_SIZE="${BROWSER_INDEED_BATCH_SIZE:-}"

if [[ -f "${WORKDIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${WORKDIR}/.env"
  set +a
fi

# Restore external environment variables (override .env values)
if [[ -n "$PRESET_BROWSER_BATCH_WORKERS" ]]; then
  export BROWSER_BATCH_WORKERS="$PRESET_BROWSER_BATCH_WORKERS"
fi
if [[ -n "$PRESET_BROWSER_LINKEDIN_BATCH_SIZE" ]]; then
  export BROWSER_LINKEDIN_BATCH_SIZE="$PRESET_BROWSER_LINKEDIN_BATCH_SIZE"
fi
if [[ -n "$PRESET_BROWSER_INDEED_BATCH_SIZE" ]]; then
  export BROWSER_INDEED_BATCH_SIZE="$PRESET_BROWSER_INDEED_BATCH_SIZE"
fi

export PYTHONPATH="${WORKDIR}/src:${PYTHONPATH:-}"
export JOB_WATCH_SOURCES="${JOB_WATCH_SOURCES:-jobvite_pragmaticplay,smartrecruitment,igamingrecruitment,igaminghunt_bamboohr,jobrapido_uae,jobleads,linkedin_public,linkedin_emea,indeed_uae}"
export SKIP_LINKEDIN_BROWSER="${SKIP_LINKEDIN_BROWSER:-0}"
export SKIP_INDEED_BROWSER="${SKIP_INDEED_BROWSER:-0}"
export SKIP_DRJOBS_BROWSER="${SKIP_DRJOBS_BROWSER:-1}"
export SKIP_GLASSDOOR_BROWSER="${SKIP_GLASSDOOR_BROWSER:-1}"
export SKIP_JOBSPY="${SKIP_JOBSPY:-0}"
export BROWSER_PROBE_HEARTBEAT_SECONDS="${BROWSER_PROBE_HEARTBEAT_SECONDS:-10}"

echo "Running one full collection pass."
echo "  Sources: ${JOB_WATCH_SOURCES}"
echo "  LinkedIn browser: $([[ "${SKIP_LINKEDIN_BROWSER}" == "1" ]] && echo off || echo on)"
echo "  Indeed browser: $([[ "${SKIP_INDEED_BROWSER}" == "1" ]] && echo off || echo on)"
echo "  Indeed JobSpy: $([[ "${SKIP_JOBSPY}" == "1" ]] && echo off || echo on)"
echo "  Telegram channels: $([[ "${SKIP_TELEGRAM_SCRAPER:-0}" == "1" ]] && echo off || echo on)"
echo "  Browser heartbeat: every ${BROWSER_PROBE_HEARTBEAT_SECONDS}s"

env PYTHONUNBUFFERED=1 BROWSER_BATCH_WORKERS="${PRESET_BROWSER_BATCH_WORKERS:-${BROWSER_BATCH_WORKERS:-1}}" BROWSER_LINKEDIN_BATCH_SIZE="${PRESET_BROWSER_LINKEDIN_BATCH_SIZE:-${BROWSER_LINKEDIN_BATCH_SIZE:-3}}" BROWSER_INDEED_BATCH_SIZE="${PRESET_BROWSER_INDEED_BATCH_SIZE:-${BROWSER_INDEED_BATCH_SIZE:-2}}" "${PYTHON_BIN}" src/watch/scraper.py collect

if [[ "${SKIP_TELEGRAM_SCRAPER:-0}" != "1" ]]; then
  echo ""
  echo "Running Telegram channel scrape..."
  env PYTHONUNBUFFERED=1 BROWSER_BATCH_WORKERS="${PRESET_BROWSER_BATCH_WORKERS:-${BROWSER_BATCH_WORKERS:-1}}" BROWSER_LINKEDIN_BATCH_SIZE="${PRESET_BROWSER_LINKEDIN_BATCH_SIZE:-${BROWSER_LINKEDIN_BATCH_SIZE:-3}}" BROWSER_INDEED_BATCH_SIZE="${PRESET_BROWSER_INDEED_BATCH_SIZE:-${BROWSER_INDEED_BATCH_SIZE:-2}}" DB_PATH="${WORKDIR}/outputs/jobs.sqlite3" "${PYTHON_BIN}" src/services/telegram_scraper.py
else
  echo "Skipping Telegram channel scrape (SKIP_TELEGRAM_SCRAPER=1)."
fi
