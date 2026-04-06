# Dashboard Modifications Guide

## Overview

This document captures all dashboard modification requests and patterns from ongoing development. Use this as a reference for future dashboard updates without repeating the same work.

**Key File**: `/Users/lewis/Desktop/agent/outputs/job_stats_dashboard.html`

**Status**: HTML is now persistent — modifications are NOT overwritten by scraper runs (as of 2026-03-28).

---

## Architecture: HTML/Data Separation

The dashboard uses a **split architecture**:
- **HTML Template** (`job_stats_dashboard.html`) — static structure, persists across scraper runs
- **Data Layer** (`outputs/jobs_analysis.json`) — dynamically loaded and updated via JavaScript
- **API Status** (`/api-status` endpoint) — real-time status of backend services

### File Flow
```
Reporter (`reporter.py`)
  ├─ save_dashboard() → creates HTML template (1st run only)
  ├─ save_dashboard_data() → saves JSON data (every run)
  └─ Existing HTML never overwritten
```

**Important**: When modifying the dashboard, changes made via browser DevTools (F12) or direct file editing are **preserved** across scraper runs.

---

## Modification Methods

### Method 1: Browser DevTools (AntiGravity/Inspector)
**Best for**: Quick visual tweaks, layout changes, styling

Steps:
1. Open dashboard in browser: `http://127.0.0.1:8765/job_stats_dashboard.html`
2. Press `F12` to open DevTools Inspector
3. Edit HTML/CSS in real-time
4. DevTools will save changes to the file
5. Refresh browser to verify

**Pros**: Visual feedback, no file reload needed
**Cons**: Changes limited to single session; need to persist manually if using plain editor

### Method 2: Direct File Edit (VS Code)
**Best for**: Structural changes, JavaScript logic, bulk edits

Steps:
1. Open file in VS Code: `/Users/lewis/Desktop/agent/outputs/job_stats_dashboard.html`
2. Make changes
3. Save (Cmd+S)
4. Refresh browser to verify

**Pros**: Full control, version control friendly
**Cons**: No visual feedback until refresh

---

## Common Modifications

### 1. Remove Unwanted Text Sections

**Request**: "Remove collection criteria text that appears above job listings"

**Location**: Search HTML for the text block you want to remove
```html
<!-- Example: "수집 기준을 먼저 보고 바로 아래에서..." text -->
```

**Method**:
- Use DevTools Inspector to find the parent `<div>` or `<section>`
- Delete the element
- Verify text is gone
- Save file

**Status**: ✅ Completed (removed 수집 기준 text block)

---

### 2. API Status Indicators

**Request**: "Show status of individual API endpoints (not all in one badge)"

**Current Implementation**:
- **3 separate status badges** in header showing:
  - Scrape State (green=online, orange=offline, red=error)
  - Watch Settings (same color scheme)
  - Reject Feedback (same color scheme)

**File**: `serve_dashboard.py` — `/api-status` endpoint
```python
{
  "timestamp": 1234567890,
  "endpoints": {
    "scrape_state": {"status": "online|offline|error", "exists": bool, "last_modified": timestamp},
    "watch_settings": {...},
    "reject_feedback": {...}
  }
}
```

**JavaScript Update Frequency**: 10 seconds (configurable in HTML)

**Status**: ✅ Completed (split into 3 badges)

---

### 3. Dashboard Data Updates (No HTML Rewrite)

**Request**: "Keep user modifications while updating job data"

**Solution**: Separate concerns
- **HTML** → saved once by `save_dashboard()` in `reporter.py`, never overwritten
- **Data** → updated by `save_dashboard_data()` in `reporter.py` every scraper run

**Code Pattern**:
```python
# reporter.py
def save_dashboard_data(data_path, stats, jobs_data):
    # Saves JSON only, does NOT touch HTML
    data_json = {
        "stats": stats,
        "jobs": jobs_data,
        "last_updated": timestamp
    }
    json.dump(data_json, open(data_path, 'w'))

# HTML fetches this JSON and displays dynamically
fetch('outputs/jobs_analysis.json').then(r => r.json()).then(data => {
    // render data
});
```

**Status**: ✅ Completed (HTML/JSON split working)

---

### 4. JavaScript Template Issues

**Issue**: Python f-string escaping conflict
```python
# ❌ WRONG
f"const interval = ${interval};"  # f-string tries to interpolate ${interval}

# ✅ CORRECT
f"const interval = ${{{interval}}};"  # Double braces escape literal ${}
```

**Status**: ✅ Fixed in `reporter.py`

---

## Monitoring & Debugging

### Check Dashboard Data
```bash
# View latest job data
cat outputs/jobs_analysis.json | jq .

# Check last update time
stat -f "%Sm" outputs/jobs_analysis.json

# Check API status
curl http://127.0.0.1:8765/api-status | jq .
```

### Check HTML Integrity
```bash
# Verify HTML file size (should be ~850KB with all data embedded)
ls -lh outputs/job_stats_dashboard.html

# Search for specific text in dashboard
grep -i "your_text_here" outputs/job_stats_dashboard.html
```

### Monitor scraper runs
```bash
# Check scrape state (updated after each scraper run)
cat outputs/scrape_state.json | jq .

# Check reject feedback (user exclusions)
cat outputs/reject_feedback.json | jq .
```

---

## Future Modification Patterns

### Pattern 1: Add New Data Field to Dashboard
1. Update `JobPosting` dataclass in `scraper.py` (or `db.py`)
2. Modify job collection logic to populate the field
3. Update `save_dashboard_data()` in `reporter.py` to include the field
4. Update HTML JavaScript to render the new field
5. No HTML regeneration needed — just modify the template

### Pattern 2: Change Layout Without Affecting Data
1. Edit HTML directly in VS Code
2. No changes to Python code needed
3. Data is fetched dynamically from JSON
4. Refresh browser to verify

### Pattern 3: Add New API Endpoint
1. Add handler to `serve_dashboard.py` (e.g., `/new-endpoint`)
2. Update HTML to call the endpoint
3. Handle response in JavaScript

### Pattern 4: Change Styling
1. Edit CSS in HTML `<style>` tag
2. Or use DevTools Inspector to adjust, then copy changes back
3. Persist by saving file

---

## Known Limitations & Workarounds

### Issue: HTML File Large (~850KB)
**Cause**: All job data is embedded in HTML as JSON at build time
**Workaround**: Keep job data in separate `jobs_analysis.json`, reference via fetch()
**Status**: ✅ Already implemented (HTML references external JSON)

### Issue: Browser Cache
**Workaround**: Serve dashboard with cache-busting headers (implemented in `serve_dashboard.py`)
```python
# HTTP headers prevent caching
self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
self.send_header("Pragma", "no-cache")
self.send_header("Expires", "0")
```

### Issue: Real-time Updates Require Page Refresh
**Current**: API status updates every 10 seconds via JavaScript fetch
**Future**: Could upgrade to WebSocket if needed

---

## Checklist for Future Modifications

- [ ] Decide: Browser DevTools vs Direct File Edit?
- [ ] Make the change
- [ ] Verify in browser (http://127.0.0.1:8765/job_stats_dashboard.html)
- [ ] Check console (F12 DevTools) for JavaScript errors
- [ ] Run scraper: `python3 scraper.py incremental`
- [ ] Verify changes persist (not overwritten)
- [ ] Test on fresh browser session (Cmd+Shift+R to hard-refresh)

---

## Files Reference

| File | Purpose | Modifiable? |
|------|---------|-----------|
| `outputs/job_stats_dashboard.html` | Dashboard template | ✅ Yes (persists) |
| `outputs/jobs_analysis.json` | Job data (auto-generated) | ⚠️ Auto-updated |
| `reporter.py` | Dashboard generator | ✅ Yes (Python logic) |
| `serve_dashboard.py` | API server | ✅ Yes (endpoints) |
| `db.py` | Database layer | ✅ Yes (data model) |
| `scraper.py` | Job collection | ✅ Yes (sources) |

---

## Recent Changes (2026-03-28)

1. **HTML/JSON Split** — HTML now persists, JSON updates dynamically
2. **API Status Badges** — 3 separate indicators for Scrape, Settings, Feedback
3. **Environment Variables** — launchd + `.env` file for auto-monitoring
4. **Reject Feedback** — Applied retroactively to existing DB jobs
5. **JavaScript Template Fix** — Corrected f-string escaping in `reporter.py`

---

## Contact & Further Help

- For scraper logic questions → see `CLAUDE.md`
- For database schema → see `db.py`
- For dashboard API → see `serve_dashboard.py`
- For data flow → see `reporter.py`
