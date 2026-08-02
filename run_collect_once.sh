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

LOCK_DIR="${WORKDIR}/outputs/run_collect_once.lockdir"
LOCK_PID_FILE="${LOCK_DIR}/pid"
GLASSDOOR_LOCK_PATH="${WORKDIR}/outputs/scrape_run.lock"
GLASSDOOR_LOCK_ACQUIRED=0
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  existing_pid="$(cat "${LOCK_PID_FILE}" 2>/dev/null || true)"
  if [[ "${existing_pid}" =~ ^[0-9]+$ ]] && kill -0 "${existing_pid}" 2>/dev/null; then
    echo "Another /run collection is already running: PID=${existing_pid}"
    exit 75
  fi
  echo "Removing stale /run collection lock: ${LOCK_DIR}"
  rm -rf "${LOCK_DIR}"
  mkdir "${LOCK_DIR}"
fi
echo "$$" > "${LOCK_PID_FILE}"
cleanup_lock() {
  if [[ "${GLASSDOOR_LOCK_ACQUIRED}" == "1" ]]; then
    lock_pid="$(cat "${GLASSDOOR_LOCK_PATH}" 2>/dev/null || true)"
    if [[ "${lock_pid}" == "$$" ]]; then
      rm -f "${GLASSDOOR_LOCK_PATH}"
    fi
  fi
  rm -rf "${LOCK_DIR}"
}
trap cleanup_lock EXIT INT TERM

phase_failures=0
failed_phases=()

record_phase_failure() {
  local phase="$1"
  local reason="$2"
  failed_phases+=("${phase}: ${reason}")
  phase_failures=$((phase_failures + 1))
}

pid_is_alive() {
  local pid="$1"
  [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null
}

db_count() {
  local sql="$1"
  "${PYTHON_BIN}" - "${WORKDIR}/outputs/jobs.sqlite3" "${sql}" <<'PY'
import sqlite3
import sys

db_path, sql = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(db_path)
try:
    value = conn.execute(sql).fetchone()[0]
    print(int(value or 0))
finally:
    conn.close()
PY
}

acquire_glassdoor_lock_or_skip() {
  if [[ "${SKIP_GLASSDOOR_BROWSER}" == "1" ]]; then
    return 0
  fi

  mkdir -p "$(dirname "${GLASSDOOR_LOCK_PATH}")"
  if [[ -f "${GLASSDOOR_LOCK_PATH}" ]]; then
    existing_pid="$(cat "${GLASSDOOR_LOCK_PATH}" 2>/dev/null || true)"
    if pid_is_alive "${existing_pid}"; then
      echo "WARNING: Glassdoor already running: PID=${existing_pid}; skipping Glassdoor phase in /run."
      export SKIP_GLASSDOOR_BROWSER=1
      export GLASSDOOR_SKIPPED_LOCKED=1
      record_phase_failure "Glassdoor" "already running"
      return 0
    fi
    echo "Removing stale Glassdoor lock: ${GLASSDOOR_LOCK_PATH}"
    rm -f "${GLASSDOOR_LOCK_PATH}"
  fi

  if ( set -C; echo "$$" > "${GLASSDOOR_LOCK_PATH}" ) 2>/dev/null; then
    GLASSDOOR_LOCK_ACQUIRED=1
  else
    existing_pid="$(cat "${GLASSDOOR_LOCK_PATH}" 2>/dev/null || true)"
    if pid_is_alive "${existing_pid}"; then
      echo "WARNING: Glassdoor already running: PID=${existing_pid}; skipping Glassdoor phase in /run."
      export SKIP_GLASSDOOR_BROWSER=1
      export GLASSDOOR_SKIPPED_LOCKED=1
      record_phase_failure "Glassdoor" "already running"
      return 0
    fi
    echo "Collection failed"
    echo "Reason:"
    echo "- initialization error: cannot acquire Glassdoor lock ${GLASSDOOR_LOCK_PATH}"
    exit 1
  fi
}

release_glassdoor_lock() {
  if [[ "${GLASSDOOR_LOCK_ACQUIRED}" != "1" ]]; then
    return 0
  fi
  lock_pid="$(cat "${GLASSDOOR_LOCK_PATH}" 2>/dev/null || true)"
  if [[ "${lock_pid}" == "$$" ]]; then
    rm -f "${GLASSDOOR_LOCK_PATH}"
  fi
  GLASSDOOR_LOCK_ACQUIRED=0
}

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

select_python_bin
log_python_bin

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

# Determine JOB_WATCH_SOURCES: external env > .env > YAML defaults
if [[ -z "${JOB_WATCH_SOURCES:-}" ]]; then
  # Try to get from YAML config
  if [[ -x "${PYTHON_BIN}" ]]; then
    YAML_SOURCES="$("${PYTHON_BIN}" -m src.utils.collection_config --enabled-job-source-ids 2>/dev/null || true)"
    if [[ -n "${YAML_SOURCES}" ]]; then
      export JOB_WATCH_SOURCES="${YAML_SOURCES}"
    else
      echo "❌ Failed to read JOB_WATCH_SOURCES from config" >&2
      exit 1
    fi
  else
    echo "❌ Python binary not available for config lookup" >&2
    exit 1
  fi
fi

export SKIP_LINKEDIN_BROWSER="${SKIP_LINKEDIN_BROWSER:-0}"
export SKIP_INDEED_BROWSER="${SKIP_INDEED_BROWSER:-0}"
export SKIP_DRJOBS_BROWSER="${SKIP_DRJOBS_BROWSER:-0}"
export SKIP_GLASSDOOR_BROWSER="${SKIP_GLASSDOOR_BROWSER:-0}"
export SKIP_JOBSPY="${SKIP_JOBSPY:-0}"
export BROWSER_PROBE_HEARTBEAT_SECONDS="${BROWSER_PROBE_HEARTBEAT_SECONDS:-10}"
export PYDANTIC_DISABLE_PLUGINS="${PYDANTIC_DISABLE_PLUGINS:-1}"
export RUN_LINKEDIN_POSTS="${RUN_LINKEDIN_POSTS:-1}"
export RUN_QUEUE_EXPORT="${RUN_QUEUE_EXPORT:-1}"

RUN_INITIAL_JOBS="$(db_count "SELECT COUNT(*) FROM jobs")"
RUN_INITIAL_LINKEDIN_POSTS="$(db_count "SELECT COUNT(*) FROM jobs WHERE source = 'linkedin_post'")"

echo "Running one full collection pass."
echo "  Sources: ${JOB_WATCH_SOURCES}"
echo "  LinkedIn browser: $([[ "${SKIP_LINKEDIN_BROWSER}" == "1" ]] && echo off || echo on)"
echo "  Indeed browser: $([[ "${SKIP_INDEED_BROWSER}" == "1" ]] && echo off || echo on)"
echo "  Indeed JobSpy: $([[ "${SKIP_JOBSPY}" == "1" ]] && echo off || echo on)"
echo "  Glassdoor: $([[ "${SKIP_GLASSDOOR_BROWSER}" == "1" ]] && echo off || echo on)"
echo "  DrJobs: $([[ "${SKIP_DRJOBS_BROWSER}" == "1" ]] && echo off || echo on)"
echo "  Telegram channels: $([[ "${SKIP_TELEGRAM_SCRAPER:-0}" == "1" ]] && echo off || echo on)"
echo "  LinkedIn posts: $([[ "${RUN_LINKEDIN_POSTS}" == "1" ]] && echo on || echo off)"
echo "  Queue export: $([[ "${RUN_QUEUE_EXPORT}" == "1" ]] && echo on || echo off)"
echo "  Browser heartbeat: every ${BROWSER_PROBE_HEARTBEAT_SECONDS}s"
echo "  Pydantic plugins: $([[ "${PYDANTIC_DISABLE_PLUGINS}" == "1" ]] && echo disabled || echo enabled)"

echo ""
echo "Running jobs/news scrape..."
acquire_glassdoor_lock_or_skip
set +e
env PYTHONUNBUFFERED=1 BROWSER_BATCH_WORKERS="${PRESET_BROWSER_BATCH_WORKERS:-${BROWSER_BATCH_WORKERS:-1}}" BROWSER_LINKEDIN_BATCH_SIZE="${PRESET_BROWSER_LINKEDIN_BATCH_SIZE:-${BROWSER_LINKEDIN_BATCH_SIZE:-3}}" BROWSER_INDEED_BATCH_SIZE="${PRESET_BROWSER_INDEED_BATCH_SIZE:-${BROWSER_INDEED_BATCH_SIZE:-2}}" "${PYTHON_BIN}" src/watch/scraper.py collect
scraper_code="$?"
set -e
release_glassdoor_lock
if [[ "${scraper_code}" != "0" ]]; then
  echo "WARNING: jobs/news scrape failed with exit code ${scraper_code}; continuing remaining /run phases."
  record_phase_failure "jobs/news scrape" "exit code ${scraper_code}"
else
  stage_failures_output="$("${PYTHON_BIN}" - <<'PY' || true
import json
from pathlib import Path

path = Path("outputs/jobs_analysis.json")
if not path.exists():
    raise SystemExit(0)
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
if not isinstance(data, dict):
    raise SystemExit(0)
metadata = data.get("collection_metadata", {})
if not isinstance(metadata, dict):
    raise SystemExit(0)
stages = metadata.get("stage_results", {})
if not isinstance(stages, dict):
    raise SystemExit(0)
for name, result in stages.items():
    if not isinstance(result, dict):
        continue
    status = result.get("status")
    if status in {"failed", "timeout", "partial", "skipped_locked"}:
        detail = result.get("detail") or status
        print(f"{name}\t{detail}")
PY
  )"
  if [[ -n "${stage_failures_output}" ]]; then
    while IFS=$'\t' read -r stage_name stage_detail; do
      [[ -n "${stage_name}" ]] || continue
      record_phase_failure "${stage_name}" "${stage_detail:-warning}"
    done <<< "${stage_failures_output}"
  fi
  "${PYTHON_BIN}" - <<'PY' || true
import json
from pathlib import Path

path = Path("outputs/jobs_analysis.json")
if not path.exists():
    raise SystemExit(0)
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
summary = (
    data.get("collection_metadata", {})
    if isinstance(data, dict)
    else {}
).get("job_mutation_summary", {})
if isinstance(summary, dict) and summary:
    print(
        "Jobs summary: "
        f"inserted={int(summary.get('inserted') or 0)} "
        f"updated={int(summary.get('updated') or 0)} "
        f"removed={int(summary.get('removed') or 0)} "
        f"final_total={int(summary.get('final_total') or 0)}"
    )
PY
fi

if [[ "${SKIP_TELEGRAM_SCRAPER:-0}" != "1" ]]; then
  echo ""
  echo "Running Telegram channel scrape..."
  TELEGRAM_TIMEOUT_SECONDS="${TELEGRAM_CHANNEL_STAGE_TIMEOUT_SECONDS:-180}"
  env PYTHONUNBUFFERED=1 BROWSER_BATCH_WORKERS="${PRESET_BROWSER_BATCH_WORKERS:-${BROWSER_BATCH_WORKERS:-1}}" BROWSER_LINKEDIN_BATCH_SIZE="${PRESET_BROWSER_LINKEDIN_BATCH_SIZE:-${BROWSER_LINKEDIN_BATCH_SIZE:-3}}" BROWSER_INDEED_BATCH_SIZE="${PRESET_BROWSER_INDEED_BATCH_SIZE:-${BROWSER_INDEED_BATCH_SIZE:-2}}" DB_PATH="${WORKDIR}/outputs/jobs.sqlite3" "${PYTHON_BIN}" src/services/telegram_scraper.py &
  telegram_pid="$!"
  telegram_started_at="$(date +%s)"
  telegram_timed_out=0
  while kill -0 "${telegram_pid}" 2>/dev/null; do
    now="$(date +%s)"
    if (( now - telegram_started_at >= TELEGRAM_TIMEOUT_SECONDS )); then
      telegram_timed_out=1
      echo "WARNING: Telegram channel scrape timed out after ${TELEGRAM_TIMEOUT_SECONDS}s; collection outputs were already saved."
      kill "${telegram_pid}" 2>/dev/null || true
      sleep 2
      kill -9 "${telegram_pid}" 2>/dev/null || true
      "${PYTHON_BIN}" -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path('src').resolve())); from utils.notifications import send_telegram_text; send_telegram_text('⚠️ Telegram channels: timeout, 수집 0건 / 저장 0건 (shell timeout)')" || true
      break
    fi
    sleep 2
  done
  if [[ "${telegram_timed_out}" == "1" ]]; then
    wait "${telegram_pid}" 2>/dev/null || true
    echo "Telegram channel scrape stage timed out."
    record_phase_failure "Telegram channels" "timeout"
  elif wait "${telegram_pid}"; then
    echo "Telegram channel scrape stage finished."
  else
    echo "WARNING: Telegram channel scrape stage failed; collection outputs were already saved."
    record_phase_failure "Telegram channels" "error"
  fi
else
  echo "Skipping Telegram channel scrape (SKIP_TELEGRAM_SCRAPER=1)."
fi

if [[ "${RUN_LINKEDIN_POSTS}" == "1" ]]; then
  echo ""
  echo "Running LinkedIn posts scrape..."
  linkedin_posts_before="$(db_count "SELECT COUNT(*) FROM jobs WHERE source = 'linkedin_post'")"
  set +e
  /bin/bash "${WORKDIR}/run_linkedin_posts.sh"
  posts_code="$?"
  set -e
  linkedin_posts_after="$(db_count "SELECT COUNT(*) FROM jobs WHERE source = 'linkedin_post'")"
  linkedin_posts_delta=$((linkedin_posts_after - linkedin_posts_before))
  linkedin_posts_inserted=0
  linkedin_posts_removed=0
  if (( linkedin_posts_delta > 0 )); then
    linkedin_posts_inserted="${linkedin_posts_delta}"
  elif (( linkedin_posts_delta < 0 )); then
    linkedin_posts_removed=$((0 - linkedin_posts_delta))
  fi
  echo "LinkedIn posts summary: inserted=${linkedin_posts_inserted} updated=0 removed=${linkedin_posts_removed} final_total=${linkedin_posts_after}"
  if [[ "${posts_code}" == "0" ]]; then
    echo "LinkedIn posts stage finished."
  else
    echo "WARNING: LinkedIn posts stage failed with exit code ${posts_code}; continuing /run."
    record_phase_failure "LinkedIn posts" "exit code ${posts_code}"
  fi
else
  echo "Skipping LinkedIn posts scrape (RUN_LINKEDIN_POSTS=${RUN_LINKEDIN_POSTS})."
fi

if [[ "${RUN_QUEUE_EXPORT}" == "1" ]]; then
  echo ""
  echo "Running queue export..."
  set +e
  queue_output="$("${PYTHON_BIN}" - <<'PY'
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path("src").resolve()))
from services.queue_exporter import export_high_scoring_jobs

result = export_high_scoring_jobs("outputs/jobs.sqlite3", min_score=60)
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
raise SystemExit(2 if result.get("status") == "failed" else 0)
PY
  )"
  queue_code="$?"
  set -e
  echo "${queue_output}"
  if [[ "${queue_code}" == "0" ]]; then
    echo "Queue export stage finished."
  else
    queue_reason="$("${PYTHON_BIN}" - "${queue_output}" <<'PY' || true
import json
import sys

try:
    data = json.loads(sys.argv[1])
except Exception:
    print("error")
    raise SystemExit(0)
error_type = data.get("error_type") or "error"
error = data.get("error") or ""
path = data.get("file_path") or ""
print(f"{error_type}: {error} path={path}".strip())
PY
    )"
    echo "WARNING: Queue export failed with exit code ${queue_code}: ${queue_reason}"
    record_phase_failure "queue export" "${queue_reason:-error}"
  fi
else
  echo "Skipping queue export (RUN_QUEUE_EXPORT=${RUN_QUEUE_EXPORT})."
fi

RUN_FINAL_JOBS="$(db_count "SELECT COUNT(*) FROM jobs")"
RUN_FINAL_LINKEDIN_POSTS="$(db_count "SELECT COUNT(*) FROM jobs WHERE source = 'linkedin_post'")"
echo "Run totals: jobs_initial=${RUN_INITIAL_JOBS} jobs_final=${RUN_FINAL_JOBS} linkedin_posts_initial=${RUN_INITIAL_LINKEDIN_POSTS} linkedin_posts_final=${RUN_FINAL_LINKEDIN_POSTS}"

if (( phase_failures > 0 )); then
  echo "Collection completed with warnings"
  echo "Final status: partial_success"
  echo "Failed phases:"
  for phase in "${failed_phases[@]}"; do
    echo "- ${phase}"
  done
  exit 2
else
  echo "Collection completed successfully"
  echo "Final status: success"
  exit 0
fi
