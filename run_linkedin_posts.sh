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
# Optional positional args to avoid shell env-var mistakes:
#   ./run_linkedin_posts.sh 36 48   # run plans 36..48
if [[ "${1:-}" =~ ^[0-9]+$ ]]; then
  export LINKEDIN_POST_START_PLAN="$1"
fi
if [[ "${2:-}" =~ ^[0-9]+$ ]]; then
  export LINKEDIN_POST_MAX_PLANS="$2"
fi
export LINKEDIN_POSTS_PROFILE_DIR="${LINKEDIN_POSTS_PROFILE_DIR:-${WORKDIR}/outputs/linkedin-post-profile}"
export LINKEDIN_POST_MAX_PLANS="${LINKEDIN_POST_MAX_PLANS:-48}"
export LINKEDIN_POST_SCROLL_ROUNDS="${LINKEDIN_POST_SCROLL_ROUNDS:-3}"
# Stability controls: run searches in small sequential batches, then cool down.
export LINKEDIN_POST_BATCH_SIZE="${LINKEDIN_POST_BATCH_SIZE:-5}"
export LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS="${LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS:-20}"
export LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS="${LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS:-35}"
export LINKEDIN_POST_QUERY_PAUSE_MIN_SECONDS="${LINKEDIN_POST_QUERY_PAUSE_MIN_SECONDS:-5}"
export LINKEDIN_POST_QUERY_PAUSE_MAX_SECONDS="${LINKEDIN_POST_QUERY_PAUSE_MAX_SECONDS:-8}"
# Default to background/headless scraping. If the session is expired, the Python
# runner opens a login browser once, then retries the scrape.
export LINKEDIN_POST_HEADLESS="${LINKEDIN_POST_HEADLESS:-1}"
export LINKEDIN_POST_AUTO_LOGIN_SETUP="${LINKEDIN_POST_AUTO_LOGIN_SETUP:-1}"
export LINKEDIN_USE_SYSTEM_CHROME="${LINKEDIN_USE_SYSTEM_CHROME:-1}"
export LINKEDIN_CDP_PORT="${LINKEDIN_CDP_PORT:-9223}"
# Each Python-managed batch disconnects/restarts the scraper Chrome profile.
export LINKEDIN_CLOSE_CHROME_AFTER="${LINKEDIN_CLOSE_CHROME_AFTER:-0}"

mkdir -p "${LINKEDIN_POSTS_PROFILE_DIR}"

# Chrome must be launched with --remote-debugging-port for the scraper to attach.
# If the same profile is already open without CDP, close it and let the probe
# reopen Chrome correctly. Login cookies remain in the profile directory.
pkill -f -- "--user-data-dir=${LINKEDIN_POSTS_PROFILE_DIR}" 2>/dev/null || true
sleep 1

if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -s "${PYTHON_BIN}" src/watch/linkedin_posts.py
fi

exec "${PYTHON_BIN}" src/watch/linkedin_posts.py
