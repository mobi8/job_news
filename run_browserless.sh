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
kill_matching_processes "browserless glassdoor probe" "browserless_glassdoor_probe.js"
kill_matching_processes "browserless scraper" "src/watch/scraper.py collect"
kill_matching_processes "playwright chrome profile" "chrome-profile-"
rm -f "${WORKDIR}/outputs/scrape_run.lock"

cd "${WORKDIR}"
JOB_WATCH_SOURCES="${JOB_WATCH_SOURCES:-glassdoor_uae}"
export BROWSER_BATCH_WORKERS="${BROWSER_BATCH_WORKERS:-1}"
if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -s env JOB_WATCH_SOURCES="${JOB_WATCH_SOURCES}" SKIP_NEWS_COLLECTION="1" "${PYTHON_BIN}" src/watch/scraper.py collect
fi

exec env JOB_WATCH_SOURCES="${JOB_WATCH_SOURCES}" SKIP_NEWS_COLLECTION="1" "${PYTHON_BIN}" src/watch/scraper.py collect
