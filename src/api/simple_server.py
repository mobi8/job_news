#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "outputs"
JOBS_DATA_PATH = OUTPUT_DIR / "jobs_analysis.json"
STATS_DATA_PATH = OUTPUT_DIR / "job_stats_data.json"
SCRAPE_STATE_PATH = OUTPUT_DIR / "scrape_state.json"
REJECT_FEEDBACK_PATH = OUTPUT_DIR / "reject_feedback.json"
JOB_STATUSES_PATH = OUTPUT_DIR / "job_statuses.json"
JOBS_DB_PATH = OUTPUT_DIR / "jobs.sqlite3"


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path.name)
    return json.loads(path.read_text(encoding="utf-8"))


def load_scrape_state() -> dict[str, Any]:
    try:
        return read_json(SCRAPE_STATE_PATH, {})
    except Exception:
        return {}


def merge_running_collection_metadata(collection_metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    scrape_state = load_scrape_state()
    if scrape_state.get("run_status") != "running":
        return collection_metadata

    running_metadata = {
        "collected_at": scrape_state.get("last_started_at") or scrape_state.get("last_scraped_at"),
        "batch_started_at": scrape_state.get("last_started_at"),
        "next_batch_at": scrape_state.get("next_scrape_at"),
        "run_status": "running",
        "new_jobs_this_run": scrape_state.get("new_jobs_this_run", 0),
        "new_news_this_run": scrape_state.get("new_news_this_run", 0),
    }
    merged = dict(collection_metadata or {})
    merged.update({k: v for k, v in running_metadata.items() if v is not None})
    return merged


def load_rejected_jobs_keys() -> set[str]:
    try:
        data = read_json(REJECT_FEEDBACK_PATH, {"rejected_jobs": []})
        return {job["key"] for job in data.get("rejected_jobs", []) if job.get("key")}
    except Exception:
        return set()


def load_job_statuses() -> dict[str, str]:
    try:
        return read_json(JOB_STATUSES_PATH, {"statuses": {}}).get("statuses", {})
    except Exception:
        return {}


def load_telegram_jobs() -> list[dict[str, Any]]:
    if not JOBS_DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(JOBS_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("select * from jobs").fetchall()
        conn.close()
    except Exception:
        return []
    return [dict(row) for row in rows if str(row["source"]).startswith("telegram_")]


def load_jobs_data() -> dict[str, Any]:
    data = read_json(JOBS_DATA_PATH)
    tg_jobs = load_telegram_jobs()
    if tg_jobs:
        data.setdefault("all_tracked_jobs", []).extend(tg_jobs)
    return data


def detect_country(job: dict[str, Any]) -> str:
    location = (job.get("location") or "").lower()
    if any(x in location for x in ["malta", "valletta", "sliema", "gzira", "몰타"]):
        return "Malta"
    if any(x in location for x in ["미국 조지아", "us georgia", "georgia, usa", "georgia, united states"]):
        return ""
    if any(x in location for x in ["georgia", "조지아", "tbilisi", "트빌리시", "batumi", "바투미"]):
        return "Georgia"
    if any(x in location for x in ["미국", "usa", "united states", "new york", "san francisco", "los angeles"]):
        return ""
    if any(x in location for x in ["hong kong", "홍콩", "hk"]):
        return ""
    if any(x in location for x in ["dubai", "두바이", "united arab emirates", "uae"]):
        return "UAE"
    return ""


def source_label(source: str) -> str:
    labels = {
        "linkedin_public": "LinkedIn",
        "indeed_uae": "Indeed UAE",
        "indeed_georgia": "Indeed Georgia",
        "indeed_malta": "Indeed Malta",
        "jobrapido_uae": "Jobrapido",
    }
    return labels.get(source, source.replace("_", " ").title())


def job_matches_filters(
    job: dict[str, Any],
    source: str | None,
    country: str | None,
    q: str | None,
    qualifies: bool | None,
    min_score: int | None,
    max_score: int | None,
) -> bool:
    if source and job.get("source") != source:
        return False
    if country and (job.get("country") or detect_country(job)).lower() != country.lower():
        return False
    if qualifies is not None and bool(job.get("qualifies")) != qualifies:
        return False
    if min_score is not None and int(job.get("match_score") or 0) < min_score:
        return False
    if max_score is not None and int(job.get("match_score") or 0) > max_score:
        return False
    if q:
        haystack = " ".join(str(job.get(k) or "") for k in ["title", "company", "location", "description"]).lower()
        if q.lower() not in haystack:
            return False
    return True


def one(params: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
    values = params.get(key)
    return values[0] if values else default


def parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "y"}


def parse_int(value: str | None, default: int | None = None) -> int | None:
    if value in {None, ""}:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class Handler(BaseHTTPRequestHandler):
    server_version = "JobWatchSimpleAPI/1.0"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        super().end_headers()

    def send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            path = parsed.path

            if path in {"/healthz", "/api/healthz"}:
                status = 200 if JOBS_DATA_PATH.exists() and STATS_DATA_PATH.exists() else 503
                self.send_json(status, {"status": "ok" if status == 200 else "missing data files"})
                return

            if path == "/api/jobs":
                self.send_json(200, self.handle_jobs(params))
                return
            if path == "/api/stats":
                self.send_json(200, self.handle_stats())
                return
            if path == "/api/recommendations":
                self.send_json(200, self.handle_recommendations(parse_int(one(params, "limit"), 10) or 10))
                return
            if path == "/api/news":
                stats = read_json(STATS_DATA_PATH)
                self.send_json(200, {
                    "news": stats.get("news_items", []),
                    "updated_at": stats.get("updated_at"),
                    "collection_metadata": merge_running_collection_metadata(stats.get("collection_metadata")),
                })
                return
            if path == "/api/topics":
                self.send_json(200, {"topics": read_json(STATS_DATA_PATH).get("topics", [])})
                return
            if path == "/api/player-mentions":
                self.send_json(200, {"player_mentions": read_json(STATS_DATA_PATH).get("player_mentions", {})})
                return
            if path == "/api/job-statuses":
                self.send_json(200, self.handle_job_statuses())
                return
            if path.startswith("/api/job/"):
                self.send_json(200, self.handle_job_detail(unquote(path.removeprefix("/api/job/"))))
                return

            self.send_json(404, {"detail": "Not found"})
        except FileNotFoundError as exc:
            self.send_json(503, {"detail": f"{exc.args[0]} not found"})
        except Exception as exc:
            self.send_json(500, {"detail": str(exc)})

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("content-length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/job-status":
                self.send_json(200, self.update_job_status(payload))
                return
            if self.path == "/telegram/webhook":
                self.send_json(200, {"ok": True})
                return
            self.send_json(404, {"detail": "Not found"})
        except Exception as exc:
            self.send_json(500, {"detail": str(exc)})

    def handle_jobs(self, params: dict[str, list[str]]) -> dict[str, Any]:
        jobs_data = load_jobs_data()
        all_jobs = jobs_data.get("all_tracked_jobs", jobs_data.get("all_jobs", jobs_data.get("filtered_jobs", [])))
        rejected = load_rejected_jobs_keys()
        filtered = [
            job for job in all_jobs
            if job.get("dashboard_key") not in rejected
            and job_matches_filters(
                job,
                one(params, "source"),
                one(params, "country"),
                one(params, "q"),
                parse_bool(one(params, "qualifies")),
                parse_int(one(params, "min_score")),
                parse_int(one(params, "max_score")),
            )
        ]
        limit = parse_int(one(params, "limit"), 50) or 50
        offset = parse_int(one(params, "offset"), 0) or 0
        paged = filtered[offset:offset + limit]
        for job in paged:
            job.setdefault("country", detect_country(job))
            job.setdefault("source_label", source_label(str(job.get("source") or "")))
        return {
            "total": len(filtered),
            "limit": limit,
            "offset": offset,
            "jobs": paged,
            "counts": {
                "recommended": sum(1 for job in filtered if job.get("qualifies")),
                "non_recommended": sum(1 for job in filtered if not job.get("qualifies")),
            },
            "collection_metadata": merge_running_collection_metadata(jobs_data.get("collection_metadata")),
        }

    def handle_stats(self) -> dict[str, Any]:
        data = read_json(STATS_DATA_PATH)
        stats = data.get("stats", {})
        return {
            "stats": stats,
            "source_total": data.get("source_total", []),
            "source_daily": data.get("source_daily", []),
            "updated_at": data.get("updated_at") or stats.get("updated_at"),
            "collection_metadata": merge_running_collection_metadata(data.get("collection_metadata")),
        }

    def handle_recommendations(self, limit: int) -> dict[str, Any]:
        data = load_jobs_data()
        recommendations = data.get("top_recommendations", [])[:limit]
        for job in recommendations:
            job.setdefault("country", detect_country(job))
            job.setdefault("source_label", source_label(str(job.get("source") or "")))
        return {"recommendations": recommendations, "count": len(recommendations)}

    def handle_job_detail(self, job_url: str) -> dict[str, Any]:
        jobs_data = load_jobs_data()
        all_jobs = jobs_data.get("all_tracked_jobs", jobs_data.get("filtered_jobs", []))
        for job in all_jobs:
            if job.get("url") == job_url:
                job.setdefault("country", detect_country(job))
                job.setdefault("source_label", source_label(str(job.get("source") or "")))
                return {"job": job}
        self.send_json(404, {"detail": f"Job not found: {job_url}"})
        return {}

    def handle_job_statuses(self) -> dict[str, Any]:
        rejected_jobs: dict[str, dict[str, Any]] = {}
        try:
            data = read_json(REJECT_FEEDBACK_PATH, {"rejected_jobs": []})
            for job in data.get("rejected_jobs", []):
                if job.get("key"):
                    rejected_jobs[job["key"]] = job
        except Exception:
            pass
        return {"statuses": load_job_statuses(), "rejected_jobs": rejected_jobs}

    def update_job_status(self, request: dict[str, Any]) -> dict[str, Any]:
        data = read_json(JOB_STATUSES_PATH, {"statuses": {}})
        statuses = data.get("statuses", {})
        job_key = request.get("job_key", "")
        status = request.get("status", "")
        if status == "unseen":
            statuses.pop(job_key, None)
        else:
            statuses[job_key] = status
        data["statuses"] = statuses
        data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

        if status == "removed":
            reject_data = read_json(REJECT_FEEDBACK_PATH, {"rejected_jobs": []})
            rejected_jobs = reject_data.get("rejected_jobs", [])
            if not any(job.get("key") == job_key for job in rejected_jobs):
                rejected_jobs.append({
                    "key": job_key,
                    "title": request.get("title", ""),
                    "company": request.get("company", ""),
                    "location": request.get("location", ""),
                    "source": request.get("source", ""),
                    "remove_reason": "",
                    "note": request.get("note", ""),
                })
                reject_data["rejected_jobs"] = rejected_jobs
                reject_data["synced_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                REJECT_FEEDBACK_PATH.write_text(json.dumps(reject_data, indent=2, ensure_ascii=False), encoding="utf-8")

        JOB_STATUSES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"success": True, "message": "Job status updated"}


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("Job Watch API running on http://127.0.0.1:8000", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
