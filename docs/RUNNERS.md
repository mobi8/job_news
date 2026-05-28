# Runner Guide

This project is split into dashboard, default full batch runners, and targeted spot runners.

## Recommended Daily Flow

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
