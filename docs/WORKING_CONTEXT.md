# Working Context

Last updated: 2026-05-08

## Branch

- Current branch: `codex/glassdoor-split`

## Dashboard UI

- Current concept: light brutalism dashboard.
- Design notes: `frontend/DESIGN_NOTES.md`
- Main UI file: `frontend/src/App.tsx`
- Main CSS file: `frontend/src/App.css`

## Dashboard/API runtime

Typical runtime:

```bash
./run_dashboard.sh
```

Manual frontend/backend during development:

```bash
cd frontend && npm run dev -- --host 0.0.0.0
uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```

## Existing scraper pipeline

Main runner:

```bash
./run_dashboard.sh
```

Heavy browserless runner:

```bash
./run_browserless.sh
```

Main scraper:

- `src/watch/scraper.py`

Flow:

```text
run_dashboard.sh
  -> FastAPI backend
  -> Vite frontend
  -> Telegram poller
  -> watch loop
  -> scraper.py
      -> LinkedIn Jobs browser
      -> Indeed browser / JobSpy
      -> Glassdoor browserless
      -> Jobvite / SmartRecruitment / Jobrapido / JobLeads
      -> GamblingCareers / Himalayas
      -> RSS news
      -> normalize -> filter -> dedupe -> score
      -> jobs.sqlite3 / jobs_analysis.json / job_stats_data.json
      -> Telegram notify
      -> career-ops queue export
```

## Telegram / career-ops integration

Relevant files:

- `src/api/telegram_poller.py`
- `src/utils/notifications.py`
- `src/services/career_bridge.py`

Current behavior:

- Telegram job cards have 2 buttons:
  - `📄 원문 JD 보기`
  - `🔍 oferta 분석`
- `oferta 분석` runs career-ops with `oferta a,b` semantics using job URL/header/JD context.
- Tested manually with a Telegram card and confirmed working.

## Georgia scraping note

- Georgia actual country updates were low.
- Many `linkedin_georgia` recent rows were actually US Georgia.
- Adjusted LinkedIn Georgia URLs toward `Tbilisi, Georgia` and added US Georgia filtering.
- Added `indeed_georgia` to default dashboard sources.

## LinkedIn Posts pipeline

Goal:

- Collect LinkedIn content/posts, not LinkedIn Jobs section.
- Manual runner separate from dashboard/browserless.
- Store as `source=linkedin_post`.
- Reuse existing DB/scoring/Telegram/dashboard as much as possible.
- User runs this manually from terminal.

Important files:

- `run_linkedin_posts.sh`
- `run_linkedin_post.sh` alias
- `setup_linkedin_posts_login.sh`
- `linkedin_posts_probe.js`
- `linkedin_posts_login_setup.js`
- `src/watch/linkedin_posts.py`
- `src/utils/config.py`
- `frontend/src/App.tsx`
- `src/utils/scoring.py`

Current runtime command:

```bash
./run_linkedin_posts.sh
```

Alias also works:

```bash
./run_linkedin_post.sh
```

## LinkedIn Posts Chrome/CDP behavior

Current design:

```text
run_linkedin_posts.sh
  -> kill any Chrome process using outputs/linkedin-post-profile
  -> launch regular Google Chrome with:
       --user-data-dir=outputs/linkedin-post-profile
       --remote-debugging-port=9223
  -> Playwright connects via CDP
  -> search LinkedIn content posts sequentially in one Chrome window/tab
```

CDP port:

```text
9223
```

Profile:

```text
outputs/linkedin-post-profile
```

Check CDP:

```bash
curl http://127.0.0.1:9223/json/version
```

Check active profile Chrome:

```bash
ps aux | grep 'linkedin-post-profile' | grep -v grep
```

Security rule:

- Do not store/use credentials in scripts.
- User logs in manually if needed.
- Use local Chrome session/cookies only.

## LinkedIn Posts query generation

Config in `src/utils/config.py`.

Keyword groups:

```py
LINKEDIN_POST_LEAD_KEYWORDS = ["hire", "hiring", "job", "job alert"]
LINKEDIN_POST_ROLE_KEYWORDS = ["crypto", "igaming", "web3", "digital asset"]
LINKEDIN_POST_LOCATION_GROUPS = [
    {"country": "UAE", "label": "UAE", "query": "in UAE"},
    {"country": "Georgia", "label": "Georgia Tbilisi", "query": "in Georgia Tbilisi"},
    {"country": "Malta", "label": "Malta", "query": "in Malta"},
]
```

Total generated search plans:

```text
4 lead keywords × 4 role keywords × 3 locations = 48 searches
```

Default runner now uses:

```bash
LINKEDIN_POST_MAX_PLANS=48
LINKEDIN_POST_SCROLL_ROUNDS=3
```

Freshness strategy:

- No date/month/year filter now.
- Freshness controlled by LinkedIn `sortBy=date_posted` and 3 scrolls per query.
- Rationale: tight date filters miss useful hidden leads.

## LinkedIn Posts link extraction

Current link priority:

1. Extract `shareId` from LinkedIn `componentkey`/translation metadata.
2. Build direct post URL:

```text
https://www.linkedin.com/feed/update/urn:li:share:{shareId}
```

3. If `ugcPostUrn` exists, use:

```text
https://www.linkedin.com/feed/update/{ugcPostUrn}
```

4. If DOM exposes actual permalink, use that.
5. Last fallback: author/company URL + stable hash.

Recent test confirmed direct post URLs are generated, e.g.:

```text
https://www.linkedin.com/feed/update/urn:li:share:7454794515866968064
```

## LinkedIn Posts partial failure handling

Problem observed:

```text
page.waitForTimeout: Target page, context or browser has been closed
```

Current behavior after fix:

- Query-level errors are caught.
- Collected posts before the error are kept.
- Probe returns partial JSON where possible.
- Python continues DB save/scoring/Telegram notification with partial results.
- Summary includes `errors=N`.

Expected final output:

```text
LinkedIn posts: raw=... filtered=... inserted=... notified=... errors=...
```

## LinkedIn Posts Telegram behavior

- DB stores all inserted leads.
- Telegram notification is bounded to top 10 newly inserted leads by match score to avoid flooding.
- If a mid-run error happens, already collected leads should still be saved and notified.

## Recent LinkedIn Posts test status

Successful small test:

```bash
LINKEDIN_POST_MAX_PLANS=2 LINKEDIN_POST_SCROLL_ROUNDS=1 ./run_linkedin_posts.sh
```

Observed result:

```text
LinkedIn posts: raw=17 filtered=11 inserted=4 notified=4 errors=0
```

Earlier successful one-query test produced 4 direct post URLs:

```text
https://www.linkedin.com/feed/update/urn:li:share:7454794515866968064
https://www.linkedin.com/feed/update/urn:li:share:7389921256843939840
https://www.linkedin.com/feed/update/urn:li:share:7378398421373681664
https://www.linkedin.com/feed/update/urn:li:share:7331306252121079808
```

## LinkedIn Posts stability mode

To reduce LinkedIn/CDP renderer failures, default runner now processes queries in small sequential batches:

```bash
LINKEDIN_POST_BATCH_SIZE=5
LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS=20
LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS=35
LINKEDIN_POST_QUERY_PAUSE_MIN_SECONDS=5
LINKEDIN_POST_QUERY_PAUSE_MAX_SECONDS=8
```

Behavior:

- One Chrome window/tab, no parallel scraping.
- Python now splits the 48 plans into 5-query batches.
- Each batch is probed, saved to DB, dashboard JSON refreshed, and Telegram notification sent immediately for newly inserted leads.
- Then scraper Chrome profile is killed/restarted and sleeps 20-35 seconds before the next batch.
- Final summary aggregates all batches.
- This LinkedIn Posts runner does not run news scraping.

Validation with shortened pauses:

```bash
LINKEDIN_POST_MAX_PLANS=6 LINKEDIN_POST_SCROLL_ROUNDS=1 \
LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS=3 LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS=5 \
LINKEDIN_POST_QUERY_PAUSE_MIN_SECONDS=1 LINKEDIN_POST_QUERY_PAUSE_MAX_SECONDS=2 \
./run_linkedin_posts.sh
```

Result:

```text
LinkedIn posts: raw=37 filtered=18 inserted=0 notified=0 errors=0
```


Latest validation after moving batching to Python:

```bash
LINKEDIN_POST_MAX_PLANS=6 LINKEDIN_POST_SCROLL_ROUNDS=1 \
LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS=3 LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS=5 \
LINKEDIN_POST_QUERY_PAUSE_MIN_SECONDS=1 LINKEDIN_POST_QUERY_PAUSE_MAX_SECONDS=2 \
./run_linkedin_posts.sh
```

Result:

```text
LinkedIn posts batch 1: raw=31 filtered=15 inserted=0 notified=0 errors=0
LinkedIn posts batch 2: raw=6 filtered=3 inserted=0 notified=0 errors=0
LinkedIn posts: raw=37 filtered=18 inserted=0 notified=0 errors=0
```

## Latest LinkedIn Posts stability update

Observed full/manual run failed around `job web3 in UAE` with:

```text
page.waitForTimeout: Target page, context or browser has been closed
```

Important: partial handling worked; run saved/notified:

```text
LinkedIn posts: raw=59 filtered=36 inserted=10 notified=10 errors=1
```

Fix applied in `linkedin_posts_probe.js`:

- Browser/page/context close errors no longer stop the whole remaining run.
- Per query retry once after restarting the scraper Chrome profile.
- Extra tabs/pages are closed between queries to reduce renderer buildup.
- Final JSON now includes `reconnects`.

Validation after fix:

```bash
LINKEDIN_POST_MAX_PLANS=12 LINKEDIN_POST_SCROLL_ROUNDS=1 ./run_linkedin_posts.sh
```

Result:

```text
LinkedIn posts: raw=65 filtered=39 inserted=4 notified=4 errors=0
```

Next recommended validation: user can rerun full default 48-plan script.

```bash
./run_linkedin_posts.sh
```

## Current next action

User is running this manually in terminal:

```bash
./run_linkedin_posts.sh
```

Need to inspect final output when user reports it:

```text
LinkedIn posts: raw=... filtered=... inserted=... notified=... errors=...
```

If errors > 0:

- Check whether DB still got new `linkedin_post` rows.
- Check if Telegram still sent top leads.
- Only debug the specific runtime error if partial handling failed.

## Validation commands

Frontend build:

```bash
cd frontend && npm run build
```

Python tests used recently:

```bash
python3 -m pytest tests/test_notifications.py tests/test_scoring.py -q
```

Syntax checks:

```bash
python3 -m py_compile src/watch/linkedin_posts.py src/utils/config.py
node --check linkedin_posts_probe.js
node --check linkedin_posts_login_setup.js
```

Inspect LinkedIn Post DB rows:

```bash
python3 - <<'PY'
import sqlite3
con=sqlite3.connect('outputs/jobs.sqlite3')
con.row_factory=sqlite3.Row
print(dict(con.execute("select count(*) c, max(first_seen_at) latest from jobs where source='linkedin_post'").fetchone()))
for r in con.execute("select first_seen_at,country,title,url,match_score from jobs where source='linkedin_post' order by first_seen_at desc limit 10"):
    print(dict(r))
PY
```

## Push history in this session

Already pushed:

- `1d74296 Refresh dashboard UI and fix review issues`
- `aaec6c0 Improve region filters and Georgia scraping`
- `f8e646a Fix Telegram oferta analysis buttons`

Unpushed likely changes:

- LinkedIn Posts pipeline files and related config/UI labels.
- `docs/WORKING_CONTEXT.md`.

## Latest LinkedIn Posts runtime fix

User run reached batch 7, then batch 8 failed at probe startup:

```text
page.goto: net::ERR_ABORTED at https://www.linkedin.com/feed/
```

Interpretation: run was interrupted at batch 8; batches 1-7 were already saved/notified because Python batch processing commits each batch immediately.

Fix applied:

- `linkedin_posts_probe.js`: feed warmup now retries once after Chrome restart for `ERR_ABORTED`, timeout, and page/browser closed errors.
- `src/watch/linkedin_posts.py`: if a whole batch fails before collecting posts, log it, count one error, cooldown, and continue next batch instead of crashing the whole run.
- Added resume env var:

```bash
LINKEDIN_POST_START_PLAN=36 LINKEDIN_POST_MAX_PLANS=48 ./run_linkedin_posts.sh
```

This resumes from plan 36 through 48.

Validation:

```bash
LINKEDIN_POST_START_PLAN=36 LINKEDIN_POST_MAX_PLANS=40 LINKEDIN_POST_SCROLL_ROUNDS=1 ./run_linkedin_posts.sh
```

Result:

```text
LinkedIn posts batch 1: raw=30 filtered=18 inserted=18 notified=6 errors=0
LinkedIn posts: raw=30 filtered=18 inserted=18 notified=6 errors=0
```

## Latest LinkedIn Posts full-run result

User resumed interrupted run with positional args:

```bash
./run_linkedin_posts.sh 36 48
```

Result:

```text
LinkedIn posts batch 1: raw=30 filtered=18 inserted=0 notified=0 errors=0
LinkedIn posts batch 2: raw=14 filtered=7 inserted=6 notified=6 errors=0
LinkedIn posts batch 3: raw=8 filtered=4 inserted=2 notified=2 errors=0
LinkedIn posts: raw=52 filtered=29 inserted=8 notified=8 errors=0
```

Together with earlier completed plans 1-35, the 48-plan LinkedIn Posts sweep is complete.

Pre-push validation passed:

```bash
node --check linkedin_posts_probe.js
node --check linkedin_posts_login_setup.js
python3 -m py_compile src/watch/linkedin_posts.py src/utils/config.py src/utils/notifications.py src/utils/scoring.py
```
