# Queue Exporter Guide

## Overview
The queue exporter automatically exports high-scoring job postings (score >= 60) from the agent's database to a JSONL queue file that career-ops can read.

## Queue File Location
- **Path**: `/Users/lewis/Desktop/career/career-ops/data/job_queue.jsonl`
- **Format**: JSONL (JSON Lines - one JSON object per line)
- **Append-only**: New jobs are appended to the file; existing jobs are not removed

## Auto-Export Integration
The queue is automatically exported after each batch run:
1. Agent's watch loop runs batch scraping
2. Upon successful completion, high-scoring jobs are extracted
3. Jobs with `match_score >= 60` are appended to the queue file
4. Log entry: "Queue export: X jobs added to career-ops"

## Queue Entry Fields
Each line in the queue file contains a JSON object with:

```json
{
  "id": "fingerprint",
  "company": "Company Name",
  "role": "Job Title",
  "score": 85,
  "description": "Full job description...",
  "url": "https://job-url.com",
  "source": "indeed_uae",
  "collected_at": "2026-04-27T11:07:49.442518+00:00",
  "exported_at": "2026-04-27T18:02:22.307011Z"
}
```

## Reading the Queue (career-ops)

### Python
```python
import json
from pathlib import Path

QUEUE_FILE = Path("/Users/lewis/Desktop/career/career-ops/data/job_queue.jsonl")

def read_queue():
    jobs = []
    with open(QUEUE_FILE, "r") as f:
        for line in f:
            if line.strip():
                jobs.append(json.loads(line))
    return jobs

# Get all jobs
all_jobs = read_queue()

# Filter by source
linkedin_jobs = [j for j in all_jobs if j["source"] == "linkedin_jobspy"]

# Filter by score
high_priority = [j for j in all_jobs if j["score"] >= 80]
```

### Processing Strategy
1. **Read**: Load jobs from the queue file
2. **Process**: Extract what you need (e.g., pull company info, draft offer analysis)
3. **Archive**: After processing, save the job ID to a "processed" list to avoid re-processing
4. **Cleanup**: Optionally archive old entries (script can provide)

## Statistics
```python
from src.services.queue_exporter import get_queue_stats

stats = get_queue_stats()
print(f"Queue size: {stats['count']}")
print(f"Avg score: {stats['avg_score']:.1f}")
print(f"Score range: {stats['min_score']}-{stats['max_score']}")
```

## Manual Operations

### Export immediately (from agent)
```bash
python3 -c "from src.services.queue_exporter import export_high_scoring_jobs; \
result = export_high_scoring_jobs('outputs/jobs.sqlite3'); \
print(f'Exported {result[\"count\"]} jobs')"
```

### Read queue from agent
```bash
python3 -c "from src.services.queue_exporter import read_queue; \
jobs = read_queue(); \
print(f'Queue has {len(jobs)} jobs')"
```

### Clear queue (use with caution)
```python
from src.services.queue_exporter import clear_queue
clear_queue()
```

## Tracking & Processing
Since the queue is append-only, career-ops should:
1. **Track processed jobs**: Keep a list of processed job IDs to avoid duplicates
2. **Use timestamps**: The `exported_at` field indicates when the job was added to the queue
3. **Consider `collected_at`**: The original collection timestamp may help identify older jobs

## Score Interpretation
- **Score >= 80**: High match - strong recommendation
- **Score 70-79**: Good match - worth reviewing
- **Score 60-69**: Moderate match - may need filtering
- **Below 60**: Excluded (not in queue)

## Integration with Applications Tracker
The queue can be integrated with `/Users/lewis/Desktop/career/career-ops/data/applications.md`:
- Process jobs from queue
- Add accepted applications to applications.md
- Link back to queue entry if needed (via job ID and source)

## Troubleshooting

### Queue file not updating
- Check watch loop logs: `/Users/lewis/Desktop/agent/logs/watch_loop.log`
- Verify career-ops data directory exists: `/Users/lewis/Desktop/career/career-ops/data/`
- Run manual export: `python3 src/services/queue_exporter.py`

### Malformed JSONL
- Each line must be valid JSON
- Common issue: newlines within descriptions (should be escaped)
- Validate with: `python3 -m json.tool < job_queue.jsonl`

### Performance with large queue
- For large queues (>10k jobs), consider streaming:
  ```python
  def stream_queue():
      with open(QUEUE_FILE, "r") as f:
          for line in f:
              if line.strip():
                  yield json.loads(line)
  ```
