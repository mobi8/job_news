#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${WORKDIR}/venv/bin/python3}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

terminate_pids() {
  local label="$1"
  shift
  local pids=("$@")
  if [[ ${#pids[@]} -eq 0 ]]; then
    return 0
  fi

  echo "  Stopping ${label}: ${pids[*]}"
  for pid in "${pids[@]}"; do
    kill -TERM "$pid" 2>/dev/null || true
  done

  local wait_count=0
  while [[ $wait_count -lt 30 ]]; do
    local still_running=0
    for pid in "${pids[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        still_running=1
        break
      fi
    done
    if [[ $still_running -eq 0 ]]; then
      return 0
    fi
    sleep 0.1
    wait_count=$((wait_count + 1))
  done

  echo "  Forcing ${label} shutdown..."
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done
}

kill_matching_processes() {
  local label="$1"
  local pattern="$2"
  local pids=()
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && pids+=("$pid")
  done < <(pgrep -f "$pattern" 2>/dev/null || true)
  if [[ ${#pids[@]} -eq 0 ]]; then
    return 0
  fi
  terminate_pids "$label" "${pids[@]}"
}

echo "Cleaning up stale browserless runs..."
kill_matching_processes "browserless scraper" "src/watch/scraper.py collect"
kill_matching_processes "browser probe" "browser_probe.js"
kill_matching_processes "playwright chrome profile" "chrome-profile-"

rm -f "${WORKDIR}/outputs/scrape_run.lock"

cd "${WORKDIR}"

# Keep the browserless runner focused on the non-Chrome job sources that are
# safe to run in the background and do not require opening the dashboard.
JOB_WATCH_SOURCES="${JOB_WATCH_SOURCES:-indeed_browserless_uae}"
export JOB_WATCH_SOURCES
export BROWSER_BATCH_WORKERS="${BROWSER_BATCH_WORKERS:-1}"
export BROWSER_INDEED_BATCH_SIZE="${BROWSER_INDEED_BATCH_SIZE:-1}"
export SKIP_LINKEDIN_BROWSER="${SKIP_LINKEDIN_BROWSER:-1}"
export SKIP_JOBSPY="${SKIP_JOBSPY:-1}"

if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -s env \
    JOB_WATCH_SOURCES="${JOB_WATCH_SOURCES}" \
    SKIP_NEWS_COLLECTION="1" \
    SKIP_LINKEDIN_BROWSER="${SKIP_LINKEDIN_BROWSER}" \
    SKIP_JOBSPY="${SKIP_JOBSPY}" \
    BROWSER_BATCH_WORKERS="${BROWSER_BATCH_WORKERS}" \
    BROWSER_INDEED_BATCH_SIZE="${BROWSER_INDEED_BATCH_SIZE}" \
    "${PYTHON_BIN}" src/watch/scraper.py collect
fi

exec env \
  JOB_WATCH_SOURCES="${JOB_WATCH_SOURCES}" \
  SKIP_NEWS_COLLECTION="1" \
  SKIP_LINKEDIN_BROWSER="${SKIP_LINKEDIN_BROWSER}" \
  SKIP_JOBSPY="${SKIP_JOBSPY}" \
  BROWSER_BATCH_WORKERS="${BROWSER_BATCH_WORKERS}" \
  BROWSER_INDEED_BATCH_SIZE="${BROWSER_INDEED_BATCH_SIZE}" \
  "${PYTHON_BIN}" src/watch/scraper.py collect
