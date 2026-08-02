# Collection Source Configuration

`collection_sources.yaml` is the single user-managed source of truth for external collection targets. Python code owns parser logic, scoring rules, regex, and runtime behavior that is not simple configuration.

## Structure

- `source_metadata`: labels, aliases, country overrides, and frontend filter metadata.
- `sources.job_pages`: fixed or explicit job pages with parser names.
- `sources.linkedin_jobs.targets`: generated or explicit LinkedIn job search targets.
- `sources.indeed.targets`: generated Indeed browser search targets.
- `sources.glassdoor`, `sources.drjobs`: keyword-driven browser/browserless targets.
- `sources.jobspy.targets`: JobSpy library targets.
- `sources.linkedin_posts`: lead x role x location plan generation.
- `sources.news_feeds`, `sources.player_feeds`: RSS feed lists.
- `keyword_groups`, `filters`, `topics`, `runtime`: shared compatibility and runtime defaults.

## Enable Or Disable A Source

Set `enabled: false` on the source or target.

```yaml
sources:
  indeed:
    targets:
      - id: indeed_uae
        enabled: false
```

## Add A Country Or Region

Add a `source_metadata` entry first, then add targets that point to its `id`.

```yaml
source_metadata:
  - id: indeed_singapore
    label: Indeed Singapore
    kind: jobs
    group: Indeed
    country: Singapore
    aliases: []
```

## Add A LinkedIn Target

Add a target under `sources.linkedin_jobs.targets`. Use `explicit_override` only when the exact URL must be preserved.

```yaml
- id: linkedin_singapore_crypto
  enabled: true
  source: linkedin_singapore
  country: Singapore
  location: Singapore
  keyword_groups:
    - id: crypto
      query: crypto OR web3 OR payments
  url:
    builder: linkedin_jobs
```

## Add An Indeed Target

Add a target under `sources.indeed.targets`. Each `keyword_groups` item generates one URL.

```yaml
- id: indeed_singapore
  enabled: true
  source: indeed_singapore
  country: Singapore
  location: singapore
  indeed_country: Singapore
  domain: sg.indeed.com
  sort: date
  keyword_groups:
    - id: crypto
      query: crypto OR web3 OR payments
  url:
    builder: indeed
```

## Add RSS Or Player Feeds

Keep feed URLs exact and set `parser: rss`.

```yaml
sources:
  news_feeds:
    - id: example_news
      enabled: true
      type: rss
      fetch_method: http
      source: rss_example_news
      label: Example News
      category: fintech
      url: https://example.com/feed/
      parser: rss
```

Player feeds use the same shape, plus `player`.

## Add A JobSpy Target

JobSpy targets are controlled by `enabled`, not by a hard-coded UAE guard.

```yaml
sources:
  jobspy:
    targets:
      - id: jobspy_singapore_indeed
        enabled: true
        site: indeed
        source: indeed_singapore
        country: Singapore
        location: Singapore
        indeed_country: Singapore
        keywords_from: indeed
```

## Add LinkedIn Posts Roles Or Locations

Plans are generated as:

```text
enabled locations * roles * leads
```

Add a role under `sources.linkedin_posts.roles`, or a location under `sources.linkedin_posts.locations`.

```yaml
- id: singapore
  enabled: true
  country: Singapore
  store_country: Singapore
  label: Singapore
  query_location: in Singapore
  location_terms:
    - singapore
```

## Validation

Run:

```bash
python3 -m src.utils.collection_config --check
```

Optional smoke checks can compare generated counts and metadata maps without running a real collection.

## Runner Python

Operational shell runners prefer `PYTHON_BIN` first, then `venv312/bin/python`, then `venv/bin/python`, then system `python3`.

Use the verified Python 3.12 environment explicitly when running collectors:

```bash
PYTHON_BIN="$PWD/venv312/bin/python" ./run_collect_once.sh
```

The runners print the selected Python path and version at startup. Python 3.14 or newer prints a dependency compatibility warning.

## Phase Runner

Collection phases are listed in `runtime.phases`. The phase runner is a thin dispatcher around the existing collectors and runners.

```bash
PYTHON_BIN="$PWD/venv312/bin/python"
$PYTHON_BIN -m src.watch.phase_runner list
$PYTHON_BIN -m src.watch.phase_runner status
$PYTHON_BIN -m src.watch.phase_runner run rss --target igaming_business --dry-run
```

Phase summaries are written under `outputs/phase_runs/` for real runs. Dry runs do not execute collectors or write summaries.

Telegram execution commands will use these environment variables for inbound authorization:

```bash
TELEGRAM_ALLOWED_CHAT_IDS=12345,67890
```

If `TELEGRAM_ALLOWED_CHAT_IDS` is not set, `TELEGRAM_CHAT_ID` is used as the single allowed chat. If neither is set, execution-style collect commands are disabled.

## Telegram Poller Launchd

Run the Telegram poller as a macOS launchd user service so it starts at login and restarts if it exits.

Install:

```bash
./install_poller_launchd.sh
```

Check status:

```bash
./status_poller_launchd.sh
```

Logs:

```bash
tail -f /tmp/jobwatch_telegram_poller.log
tail -f /tmp/jobwatch_telegram_poller.error.log
```

Restart:

```bash
launchctl kickstart -k gui/$(id -u)/com.jobwatch.telegram-poller
```

Remove:

```bash
./uninstall_poller_launchd.sh
```

`run_poller.sh` no longer starts a detached background process by default. If launchd is installed, it shows service status. For a temporary terminal-bound run, use:

```bash
./run_poller.sh --foreground
```

## Override Priority

Runtime values use this priority:

```text
environment variable > YAML > code default
```

Source lists and targets should be edited in YAML. Use environment variables only for runtime overrides such as lookback windows, batch sizes, and source selection.

## Common Mistakes

- Changing a target `id` without updating related metadata or stored expectations.
- Adding a new `source` without a matching `source_metadata` entry.
- Putting parser logic, regex, or scoring rules in YAML.
- Editing generated URL strings instead of changing `location`, `geo_id`, `domain`, or `keyword_groups`.
- Removing `parser: rss` from feeds.
- Adding LinkedIn Posts locations without `location_terms`, which weakens filtering.
- Forgetting that disabling one LinkedIn Posts location changes the plan count.
