# Runner Guide & Technical Reference

This project is split into dashboard, default full batch runners, and targeted spot runners.

## Quick Start: Recommended Daily Flow

### 1. Dashboard only

```bash
./run_dashboard.sh
```

- Starts: backend API and frontend dashboard.
- Does not scrape.
- Use this when you only want to review saved jobs.
- URL: `http://localhost:4173/`

### 2. One full batch scrape

```bash
./run_collect_once.sh
```

- Runs once and exits.
- Default sources:
  - `jobvite_pragmaticplay`
  - `smartrecruitment`
  - `igamingrecruitment`
  - `igaminghunt_bamboohr`
  - `jobrapido_uae`
  - `jobleads`
  - `linkedin_public`
  - `linkedin_emea`
  - `indeed_uae`
- Default geo:
  - Company boards: board-defined, mostly UAE / Dubai / remote / company locations.
  - LinkedIn public: UAE / Dubai and EMEA remote searches from `LINKEDIN_SEARCH_URLS`.
  - Indeed: UAE / Dubai searches from `INDEED_SEARCH_URLS` and JobSpy UAE plan.
  - Telegram: configured public job channels, saved as UAE-oriented Telegram sources.
- Method:
  - Company boards: direct HTTP/API/HTML parsing.
  - LinkedIn: Playwright browser probe, not LinkedIn spot.
  - Indeed: Playwright browser probe plus JobSpy.
  - Telegram: public channel scraper after the main batch.

### 3. Continuous full watch

```bash
./run_watch_loop.sh
```

- Runs repeatedly based on `outputs/watch_settings.json`.
- Default interval fallback: 120 minutes.
- Default sources and methods are the same full batch set as `run_collect_once.sh`.
- Telegram channel scraping runs after each successful main batch.
- LinkedIn spot remains skipped by default, because it is a targeted command flow.
- Use this for background monitoring.

## Heavy Runners

### LinkedIn jobs board spot search

```bash
./run_linkedin_jobs_spot.sh "Dubai, United Arab Emirates" "web3,crypto payments" 3
```

- Source written as: `linkedin_job_spot`.
- Geo: first argument, for example `Dubai, United Arab Emirates`, `Malta`, `Georgia`, `Amsterdam`.
- Keywords: second argument, comma-separated.
- Limit: third argument.
- Method: Chrome CDP / LinkedIn jobs search pages.
- Use for targeted, manual LinkedIn job-board checks.

### LinkedIn posts spot search

```bash
./run_linkedin_posts.sh spot "Dubai, United Arab Emirates" "crypto,web3,payments" 5
```

- Source written as: `linkedin_post_spot`.
- Geo: first argument after `spot`.
- Keywords: second argument, comma-separated.
- Limit: third argument.
- Method: authenticated LinkedIn post search using the saved Chrome profile in `outputs/linkedin-post-profile`.
- First-time setup:

```bash
./setup_linkedin_posts_login.sh
```

### LinkedIn combined spot set

```bash
./run_linkedin_spot_set.sh "Dubai, United Arab Emirates" "crypto,web3,payments" 5
```

- Runs both:
  - `run_linkedin_posts.sh spot ...`
  - `run_linkedin_jobs_spot.sh ...`
- Does not run news or company-board scraping.
- This is separate from the default LinkedIn batch. The default batch uses public LinkedIn jobs search URLs; spot uses your Telegram/manual location + keyword command.
- Use when you want a targeted LinkedIn sweep across posts and jobs.

### Glassdoor

```bash
./run_glassdoor.sh
```

- Source: `glassdoor_uae`.
- Geo: UAE-oriented Glassdoor keyword pages.
- Keywords:
  - crypto
  - igaming
  - payment
  - wallet
  - digital asset
  - product
  - backlog
- Method: Browserless / remote browser probe.
- Heavy and slower; run manually.

`run_browserless.sh` is just an alias for `run_glassdoor.sh`.

## Old Combined Mode

```bash
./run_dashboard.sh --with-workers
```

- Starts dashboard, Telegram poller, and watch loop in one terminal.
- This is the old heavy style.
- Prefer separate runners unless you intentionally want everything tied together.

## Source / Geo / Method Map

| Source | Default Geo | Method | Default Runner |
| --- | --- | --- | --- |
| `jobvite_pragmaticplay` | Board-defined, often global/remote/company locations | direct HTTP parse | `run_collect_once.sh`, `run_watch_loop.sh` |
| `smartrecruitment` | Board-defined | direct HTTP/API parse | `run_collect_once.sh`, `run_watch_loop.sh` |
| `igamingrecruitment` | Board-defined, UAE-focused in current config | direct HTML parse | `run_collect_once.sh`, `run_watch_loop.sh` |
| `igaminghunt_bamboohr` | Board-defined | embedded BambooHR parse | `run_collect_once.sh`, `run_watch_loop.sh` |
| `jobrapido_uae` | UAE / Dubai | direct HTML parse | `run_collect_once.sh`, `run_watch_loop.sh` |
| `jobleads` | UAE / Ras Al Khaimah query | direct HTML parse | `run_collect_once.sh`, `run_watch_loop.sh` |
| `linkedin_public` | UAE / Dubai | Playwright public LinkedIn jobs | `run_collect_once.sh`, `run_watch_loop.sh` |
| `linkedin_emea` | EMEA remote | Playwright public LinkedIn jobs | `run_collect_once.sh`, `run_watch_loop.sh` |
| `indeed_uae` | UAE / Dubai | Playwright Indeed plus JobSpy | `run_collect_once.sh`, `run_watch_loop.sh` |
| `telegram_*` | UAE-oriented public channels | public Telegram channel scrape | `run_collect_once.sh`, `run_watch_loop.sh` |
| `linkedin_job_spot` | user argument | Chrome CDP targeted LinkedIn jobs | `run_linkedin_jobs_spot.sh`, `run_linkedin_spot_set.sh`, Telegram `spot` command |
| `linkedin_post_spot` | user argument | authenticated targeted LinkedIn posts | `run_linkedin_posts.sh spot`, `run_linkedin_spot_set.sh`, Telegram `spot` command |
| `glassdoor_uae` | UAE | Browserless | `run_glassdoor.sh` |

## Advanced Overrides

Run only one source:

```bash
JOB_WATCH_SOURCES=jobvite_pragmaticplay ./run_collect_once.sh
```

Disable heavy browser sources for a lighter batch:

```bash
SKIP_LINKEDIN_BROWSER=1 SKIP_INDEED_BROWSER=1 SKIP_JOBSPY=1 SKIP_TELEGRAM_SCRAPER=1 ./run_collect_once.sh
```

Run continuous watch with LinkedIn job spot enabled too:

```bash
SKIP_LINKEDIN_JOB_SPOT=0 ./run_watch_loop.sh
```

Run only default LinkedIn public batch:

```bash
JOB_WATCH_SOURCES=linkedin_public,linkedin_emea SKIP_INDEED_BROWSER=1 SKIP_JOBSPY=1 SKIP_TELEGRAM_SCRAPER=1 ./run_collect_once.sh
```

Run only default Indeed batch:

```bash
JOB_WATCH_SOURCES=indeed_uae SKIP_LINKEDIN_BROWSER=1 SKIP_TELEGRAM_SCRAPER=1 ./run_collect_once.sh
```

LinkedIn/Indeed browser modes are heavier and more likely to hit timeouts or anti-bot checks.

---

# Technical Reference: Runner Implementation Details

All shell runner scripts (run_*.sh) in the repository root are thin wrappers that orchestrate Python entry points and service lifecycle management.

## Runner Implementation Summary

| Runner | Entry Point(s) | Lifecycle |
|--------|---|---|
| `run_collect_once.sh` | `src/watch/scraper.py collect` | One-shot orchestrator |
| `run_dashboard.sh` | `src/api/simple_server.py` + `src/api/static_frontend_server.py` | Long-running (API + Frontend) |
| `run_poller.sh` | `src/api/telegram_poller.py` | Long-running (Telegram service) |
| `run_watch_loop.sh` | `src/watch/loop.py` | Long-running (continuous) |
| `run_glassdoor.sh` | `src/watch/glassdoor_batch.py` | Long-running (batch) |
| `run_linkedin_posts.sh` | `src/watch/linkedin_posts.py` | Long-running (with timeout) |
| `run_linkedin_jobs_spot.sh` | `src/watch/linkedin_jobs_spot.py` | One-shot or batch |
| `run_browserless.sh` | `run_glassdoor.sh` (wrapper) | Wrapper |
| `run_linkedin_post.sh` | `run_linkedin_posts.sh` (wrapper) | Wrapper |
| `run_linkedin_spot_set.sh` | `run_linkedin_posts.sh` + `run_linkedin_jobs_spot.sh` | Orchestrator (sequential) |

## Detailed Implementation Notes

### `run_collect_once.sh`
**Entry Point:** `src/watch/scraper.py collect`

A complex orchestrator that runs one complete collection pass:
- **Main scrape** → `src/watch/scraper.py collect`
- **Telegram channels** → `src/services/telegram_scraper.py` subprocess with 180-second timeout
- **LinkedIn posts** → `/bin/bash run_linkedin_posts.sh` subprocess
- **Queue export** → `services.queue_exporter.export_high_scoring_jobs` inline Python

**Locking:**
- Lock directory: `outputs/run_collect_once.lockdir/` with PID tracking
- Glassdoor lock: `outputs/scrape_run.lock` to prevent concurrent Glassdoor scraping across runners

**Exit Codes:**
- 0: Success
- 2: Partial success (some phases failed)
- 75: Another /run already in progress

---

### `run_dashboard.sh`
**Entry Points:**
- Backend: `src/api/simple_server.py` (spins a ThreadingHTTPServer on port 8000)
- Frontend: `src/api/static_frontend_server.py` (static file server on port 4173)
- Frontend build: esbuild via `./node_modules/.bin/esbuild`

**Health Checks:**
- Backend: HTTP GET to `http://127.0.0.1:8000/api/healthz` (60-second timeout)
- Frontend: Grep for log message in output (60-second timeout)

**Process Management:**
- Cleans up orphaned processes on ports 8000, 4173, 5173 before startup
- Graceful shutdown with 10-second grace period; force-kill after timeout

**Frontend Build Logic:**
- Checks if build is needed (source files newer than dist/assets/app.js)
- Uses esbuild to bundle TypeScript with tsx loader
- Generates dist/index.html on-demand

---

### `run_poller.sh`
**Entry Point:** `src/api/telegram_poller.py`

**Behavior:**
1. Checks if launchd service is installed; if yes, displays status via `status_poller_launchd.sh`
2. Checks if poller process already running (via pgrep); if yes, displays PID
3. Otherwise shows installation instructions

**Foreground Mode:** `./run_poller.sh --foreground` executes Python directly
**Process Detection:** `pgrep -f "src/api/telegram_poller.py"`

---

### `run_watch_loop.sh`
**Entry Point:** `src/watch/loop.py`

**Special Features:**
- Uses `caffeinate -s` on macOS to prevent system sleep
- Exports PYTHONPATH and sets SKIP_* environment flags
- Continuous loop based on `outputs/watch_settings.json` configuration

---

### `run_glassdoor.sh`
**Entry Point:** `src/watch/glassdoor_batch.py`

**Environment Variables:**
- JOB_WATCH_SOURCES: Default "glassdoor_uae"
- GLASSDOOR_ONLY: Set to "1" to prevent other sources
- SKIP_NEWS: Set to "1"
- BROWSER_BATCH_*: Control batch sizing and worker counts

**Special Features:**
- Uses `caffeinate -s` on macOS to prevent system sleep
- Supports COLLECTION_TARGET_FILTER_JSON for targeted filtering

---

### `run_linkedin_posts.sh`
**Entry Point:** `src/watch/linkedin_posts.py`

**Locking:**
- Lock file: `outputs/linkedin_posts.lock` (JSON file with PID + start timestamp)
- Prevents concurrent runs via PID checking

**Key Features:**
- Timeout enforcement: LINKEDIN_POST_TOTAL_TIMEOUT_SECONDS (default 5400s = 90 min)
- Spot mode: `./run_linkedin_posts.sh spot <location> <keywords> <limit>`
- One-shot mode: LINKEDIN_POST_ONCE=1
- Plan range mode: `./run_linkedin_posts.sh 36 48`

**Configuration:**
- LINKEDIN_CDP_PORT: Chrome DevTools Protocol port (default 9223)
- LINKEDIN_USE_SYSTEM_CHROME: Use system Chrome vs bundled (default 1)
- LINKEDIN_POST_HEADLESS: Headless mode (default 1)
- LINKEDIN_CLOSE_CHROME_AFTER: Close Chrome after collection (default 0)

---

### `run_linkedin_jobs_spot.sh`
**Entry Point:** `src/watch/linkedin_jobs_spot.py`

**Arguments:**
Accepts location-based or keyword-based filtering arguments passed through to Python script.

**Environment Variables:**
- BROWSER_HEADLESS: Headless mode (default 1)
- BROWSER_PROBE_HEARTBEAT_SECONDS: Status check interval (default 10)

---

### `run_browserless.sh`
**Implementation:** Simple wrapper that redirects all arguments to `run_glassdoor.sh`

---

### `run_linkedin_post.sh`
**Implementation:** Simple wrapper that redirects all arguments to `run_linkedin_posts.sh`

---

### `run_linkedin_spot_set.sh`
**Orchestrator Logic:**
1. Calls `run_linkedin_posts.sh spot <location> <keywords> <limit>`
2. Calls `run_linkedin_jobs_spot.sh <location> <keywords> <limit>`
3. Enforces mutual exclusion via lock directory

---

## Python Selection Algorithm

All runners implement the same Python selection (function `select_python_bin()`):

1. **Environment variable:** If `PYTHON_BIN` is set and executable, use it
2. **Virtual environment (3.12):** If `./venv312/bin/python` exists and is executable, use it
3. **Virtual environment (generic):** If `./venv/bin/python` exists and is executable, use it
4. **System Python:** Use `python3` from PATH (fails if not found)

Version warning: Issues warning if Python >= 3.14 is detected (current dependencies pinned to 3.12)

---

## Locking & Concurrency Mechanisms

| Runner | Lock | Type | Location |
|--------|------|------|----------|
| `run_collect_once.sh` | Run lock | Directory + PID | `outputs/run_collect_once.lockdir/pid` |
| `run_collect_once.sh` | Glassdoor lock | File + PID | `outputs/scrape_run.lock` |
| `run_linkedin_posts.sh` | Posts lock | File (JSON) | `outputs/linkedin_posts.lock` |
| `run_linkedin_spot_set.sh` | Spot set lock | Directory | `outputs/linkedin-spot-set.lock` |

---

## Process Lifecycle Patterns

### One-Shot (Exit on Completion)
- `run_collect_once.sh`: Runs one full pass, reports summary, exits with status code
- `run_linkedin_jobs_spot.sh`: Runs scraping, exits when complete

### Long-Running (Until Interrupted)
- `run_watch_loop.sh`: Continuous loop with configurable interval
- `run_poller.sh --foreground`: Terminal-bound service
- `run_glassdoor.sh`: Batch processing until complete
- `run_linkedin_posts.sh`: Scrapes until timeout or completion
- `run_dashboard.sh`: Runs until user Ctrl-C or TERM signal

### Orchestrator (Calls Other Runners)
- `run_collect_once.sh`: Calls Telegram scraper subprocess, LinkedIn posts runner subprocess, queue exporter inline
- `run_linkedin_spot_set.sh`: Calls both LinkedIn runners sequentially with shared lock

### Wrapper/Alias (Delegates to Another Runner)
- `run_browserless.sh`: Delegates to `run_glassdoor.sh`
- `run_linkedin_post.sh`: Delegates to `run_linkedin_posts.sh`

---

## Exit Codes Reference

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error / initialization failure |
| 2 | Usage error OR partial success with phase failures (run_collect_once.sh only) |
| 75 | Already running (run_collect_once.sh or run_linkedin_posts.sh) |
| 124 | Timeout exceeded (run_linkedin_posts.sh) |

---

## Integration Patterns

### Dashboard + Watch Loop
- Dashboard starts API + frontend only (doesn't scrape)
- Watch loop runs independently, typically via launchd or manual terminal
- Both can run simultaneously without port or database conflicts

### Telegram Poller Integration
- Dashboard does NOT start Telegram poller
- Poller managed by launchd (macOS) or manual `./run_poller.sh --foreground`
- Poller listens for /collect, /pause, /resume Telegram commands
- Commands trigger Python functions via subprocess or direct imports

### Collection Orchestration
- `run_collect_once.sh` is main orchestrator
- `run_linkedin_spot_set.sh` is secondary orchestrator for LinkedIn-only flows
- All sub-runners inherit PYTHONPATH and environment from parent shell
