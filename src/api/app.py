from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path so utils can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.career_bridge import run, route_command
from utils.config import OUTPUT_DIR
from utils.scoring import source_label

app = FastAPI(
    title="Job Watch API",
    description="이 API는 기존 Python 대시보드에 쓰인 stats / job 데이터를 JS 프론트엔드에서 소비할 수 있게 노출합니다.",
)

# Enable CORS for frontend dev server and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4173", "http://localhost:5173", "http://127.0.0.1:4173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS_DATA_PATH = OUTPUT_DIR / "jobs_analysis.json"
STATS_DATA_PATH = OUTPUT_DIR / "job_stats_data.json"
SCRAPE_STATE_PATH = OUTPUT_DIR / "scrape_state.json"
REJECT_FEEDBACK_PATH = OUTPUT_DIR / "reject_feedback.json"
JOB_STATUSES_PATH = OUTPUT_DIR / "job_statuses.json"


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"{path.name} not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse {path.name}: {exc}")


def load_jobs_data() -> Dict[str, Any]:
    data = read_json(JOBS_DATA_PATH)
    # Add Telegram jobs from database
    from utils.db import Database
    db = Database(OUTPUT_DIR / "jobs.sqlite3")
    all_jobs = db.fetch_all_jobs()
    tg_jobs = [job for job in all_jobs if job.get("source", "").startswith("telegram_")]
    if tg_jobs:
        data.setdefault("all_tracked_jobs", []).extend(tg_jobs)
    return data


def load_stats_data() -> Dict[str, Any]:
    return read_json(STATS_DATA_PATH)


def load_scrape_state() -> Dict[str, Any]:
    if not SCRAPE_STATE_PATH.exists():
        return {}
    try:
        return json.loads(SCRAPE_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def merge_running_collection_metadata(collection_metadata: Dict[str, Any] | None) -> Dict[str, Any] | None:
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
    if collection_metadata:
        merged = dict(collection_metadata)
        merged.update({k: v for k, v in running_metadata.items() if v is not None})
        return merged
    return running_metadata


def load_rejected_jobs_keys() -> set[str]:
    """Load rejected job keys from reject_feedback.json"""
    if not REJECT_FEEDBACK_PATH.exists():
        return set()
    try:
        data = json.loads(REJECT_FEEDBACK_PATH.read_text(encoding="utf-8"))
        return {job["key"] for job in data.get("rejected_jobs", [])}
    except Exception:
        return set()


class JobStatusRequest(BaseModel):
    job_key: str
    status: str  # "unseen", "viewed", "applied", "removed"
    title: str = ""
    company: str = ""
    location: str = ""
    source: str = ""
    note: str = ""


def load_job_statuses() -> Dict[str, str]:
    """Load all job statuses from job_statuses.json"""
    if not JOB_STATUSES_PATH.exists():
        return {}
    try:
        data = json.loads(JOB_STATUSES_PATH.read_text(encoding="utf-8"))
        return data.get("statuses", {})
    except Exception:
        return {}


def detect_country(job: Dict[str, Any]) -> str:
    location = (job.get("location") or "").lower()

    # First check for Malta (high priority)
    if "malta" in location or "valletta" in location or "몰타" in location or "sliema" in location or "gzira" in location:
        return "Malta"

    # Then check for Georgia (before USA exclusions to catch Georgia properly)
    # Must check for "미국 조지아" (US Georgia) first
    if "미국 조지아" in location or "us georgia" in location or "georgia, usa" in location or "georgia, united states" in location:
        return ""
    if "georgia" in location or "조지아" in location or "tbilisi" in location or "트빌리시" in location or "batumi" in location or "바투미" in location:
        return "Georgia"

    # Exclude USA
    usa_keywords = [
        "미국", "usa", "united states", "american gaming", "ags -", "fanduel",
        "atlanta", "duluth", "alpharetta", "sandy springs", "remote in", "acc", "anduril",
        "new york", "san francisco", "los angeles", "chicago", "boston", "seattle",
        "austin", "denver", "miami", "portland", "denver", "united states",
    ]
    if any(x in location for x in usa_keywords):
        return ""

    # Exclude Hong Kong
    if "hong kong" in location or "홍콩" in location or "hk" in location:
        return ""

    if "dubai" in location or "두바이" in location or "united arab emirates" in location or "uae" in location:
        return "UAE"
    return ""


def job_matches_filters(
    job: Dict[str, Any],
    source: Optional[str],
    country: Optional[str],
    q: Optional[str],
    qualifies: Optional[bool],
    min_score: Optional[int],
    max_score: Optional[int],
) -> bool:
    if source and job.get("source") != source:
        return False

    if country:
        job_country = job.get("country") or detect_country(job)
        if job_country.lower() != country.lower():
            return False

    if qualifies is not None and bool(job.get("qualifies")) != qualifies:
        return False

    if min_score is not None and job.get("match_score", 0) < min_score:
        return False

    if max_score is not None and job.get("match_score", 0) > max_score:
        return False

    if q:
        haystack = " ".join(
            filter(
                None,
                [
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                    job.get("description", ""),
                ],
            )
        ).lower()
        if q.lower() not in haystack:
            return False

    return True


@app.get("/api/jobs", summary="Filtered job list")
def get_jobs(
    source: Optional[str] = Query(
        None,
        description="소스 이름 (e.g., linkedin_public, indeed_uae, telegram_job_crypto_uae)",
    ),
    country: Optional[str] = Query(None, description="국가명 (예: UAE, Georgia, Malta)"),
    q: Optional[str] = Query(None, description="제목·회사·지역 검색"),
    qualifies: Optional[bool] = Query(
        None,
        description="추천 공고만 (true/false). 지정하지 않으면 전체.",
    ),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    max_score: Optional[int] = Query(None, ge=0, le=100),
    limit: Optional[int] = Query(50, gt=0),
    offset: Optional[int] = Query(0, ge=0),
) -> Dict[str, Any]:
    jobs_data = load_jobs_data()
    # Use all_tracked_jobs which contains the full historical data
    all_jobs = jobs_data.get("all_tracked_jobs", jobs_data.get("filtered_jobs", []))

    # Filter out rejected jobs
    rejected_keys = load_rejected_jobs_keys()
    all_jobs = [job for job in all_jobs if job.get("dashboard_key") not in rejected_keys]

    filtered = [
        job
        for job in all_jobs
        if job_matches_filters(job, source, country, q, qualifies, min_score, max_score)
    ]
    total = len(filtered)
    slice_start = offset
    slice_end = offset + limit
    paged = filtered[slice_start:slice_end]
    for job in paged:
        job.setdefault("country", detect_country(job))
        job.setdefault("source_label", source_label(job.get("source", "")))
    # Calculate counts based on all filtered jobs, not just paged results
    recommended_count = sum(1 for job in filtered if job.get("qualifies"))
    non_recommended_count = sum(1 for job in filtered if not job.get("qualifies"))

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "jobs": paged,
        "counts": {
            "recommended": recommended_count,
            "non_recommended": non_recommended_count,
        },
        "collection_metadata": merge_running_collection_metadata(jobs_data.get("collection_metadata")),
    }


@app.get("/api/stats", summary="Dashboard statistics")
def get_stats() -> Dict[str, Any]:
    data = load_stats_data()
    stats = data.get("stats", {})
    return {
        "stats": stats,
        "source_total": data.get("source_total", []),
        "source_daily": data.get("source_daily", []),
        "updated_at": data.get("updated_at") or stats.get("updated_at"),
        "collection_metadata": merge_running_collection_metadata(data.get("collection_metadata")),
    }


@app.get("/api/recommendations", summary="Top recommendations")
def get_recommendations(limit: int = Query(10, gt=0, le=50)) -> Dict[str, Any]:
    data = load_jobs_data()
    recommendations = data.get("top_recommendations", [])[:limit]
    for job in recommendations:
        job.setdefault("country", detect_country(job))
        job.setdefault("source_label", source_label(job.get("source", "")))
    return {"recommendations": recommendations, "count": len(recommendations)}


@app.get("/api/news", summary="Recent news items")
def get_news() -> Dict[str, Any]:
    stats = load_stats_data()
    return {
        "news": stats.get("news_items", []),
        "updated_at": stats.get("updated_at"),
        "collection_metadata": merge_running_collection_metadata(stats.get("collection_metadata")),
    }


@app.get("/api/topics", summary="News topics")
def get_topics() -> Dict[str, Any]:
    stats = load_stats_data()
    return {"topics": stats.get("topics", [])}


@app.get("/api/player-mentions", summary="Player mentions")
def get_player_mentions() -> Dict[str, Any]:
    stats = load_stats_data()
    return {"player_mentions": stats.get("player_mentions", {})}


@app.get("/api/job/{job_url:path}", summary="Get job detail with description")
def get_job_detail(job_url: str) -> Dict[str, Any]:
    """Get full job details including description by url"""
    jobs_data = load_jobs_data()
    all_jobs = jobs_data.get("all_tracked_jobs", jobs_data.get("filtered_jobs", []))

    for job in all_jobs:
        if job.get("url") == job_url:
            job.setdefault("country", detect_country(job))
            job.setdefault("source_label", source_label(job.get("source", "")))
            return {"job": job}

    raise HTTPException(status_code=404, detail=f"Job not found: {job_url}")


@app.get("/api/job-statuses")
def get_job_statuses() -> Dict[str, Any]:
    """Get all job statuses and rejected job details"""
    statuses = load_job_statuses()

    # Load rejected jobs for details
    rejected_jobs: Dict[str, Dict[str, Any]] = {}
    if REJECT_FEEDBACK_PATH.exists():
        try:
            data = json.loads(REJECT_FEEDBACK_PATH.read_text(encoding="utf-8"))
            for job in data.get("rejected_jobs", []):
                rejected_jobs[job.get("key")] = job
        except Exception:
            pass

    return {"statuses": statuses, "rejected_jobs": rejected_jobs}


@app.post("/api/job-status")
def update_job_status(request: JobStatusRequest) -> Dict[str, Any]:
    """Update a job's status (viewed, applied, removed, unseen)"""
    try:
        # Load existing statuses
        if JOB_STATUSES_PATH.exists():
            data = json.loads(JOB_STATUSES_PATH.read_text(encoding="utf-8"))
        else:
            data = {"statuses": {}}

        statuses: Dict[str, str] = data.get("statuses", {})

        # Update or set the status
        if request.status == "unseen":
            # Remove from tracking if set back to unseen
            statuses.pop(request.job_key, None)
        else:
            statuses[request.job_key] = request.status

        data["statuses"] = statuses
        data["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Also update reject_feedback.json if removing
        if request.status == "removed":
            if REJECT_FEEDBACK_PATH.exists():
                reject_data = json.loads(REJECT_FEEDBACK_PATH.read_text(encoding="utf-8"))
            else:
                reject_data = {"rejected_jobs": []}

            rejected_jobs: List[Dict[str, Any]] = reject_data.get("rejected_jobs", [])
            existing = next((j for j in rejected_jobs if j["key"] == request.job_key), None)

            if not existing:
                rejected_jobs.append({
                    "key": request.job_key,
                    "title": request.title,
                    "company": request.company,
                    "location": request.location,
                    "source": request.source,
                    "remove_reason": "",
                    "note": request.note,
                })
                reject_data["rejected_jobs"] = rejected_jobs
                reject_data["synced_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                REJECT_FEEDBACK_PATH.write_text(json.dumps(reject_data, indent=2, ensure_ascii=False))
                if hasattr(load_rejected_jobs_keys, 'cache_clear'):
                    load_rejected_jobs_keys.cache_clear()

        # Write job statuses
        JOB_STATUSES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))

        return {"success": True, "message": "Job status updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update job status: {str(e)}")


@app.get("/healthz")
@app.get("/api/healthz")
def health_check() -> JSONResponse:
    if not JOBS_DATA_PATH.exists() or not STATS_DATA_PATH.exists():
        return JSONResponse(status_code=503, content={"status": "missing data files"})
    return JSONResponse(status_code=200, content={"status": "ok"})


@app.post("/telegram/webhook")
async def telegram_webhook(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle incoming Telegram messages"""
    try:
        import os
        from datetime import datetime, timedelta

        if "message" not in data:
            return {"ok": True}

        msg = data["message"]
        text = msg.get("text", "").strip()
        chat_id = msg.get("chat", {}).get("id")

        if not text or not chat_id:
            return {"ok": True}

        mode, query = route_command(text)
        if mode:
            from utils.notifications import send_telegram_text

            if not query:
                if mode == "oferta":
                    send_telegram_text("사용법: 분석. 회사명 포지션 위치\n예) 분석. Stake.com Product Manager UAE")
                elif mode == "deep":
                    send_telegram_text("사용법: deep. 회사명 또는 URL\n예) deep. Stake.com")
                else:
                    send_telegram_text(f"사용법: {mode}. 질문")
                return {"ok": True}

            label = {
                "oferta": "분석",
                "deep": "회사정보",
                "contacto": "연락",
            }.get(mode, mode)
            send_telegram_text(f"🔍 career-ops {label} 중...\n{query}")
            result = run(mode, query)
            if len(result) <= 4000:
                send_telegram_text(result)
            else:
                for i in range(0, len(result), 4000):
                    send_telegram_text(result[i:i + 4000])
            return {"ok": True}

        # Parse days from message ("최근 3일", "3일" 등)
        days = 7  # default
        if "3일" in text or "3day" in text:
            days = 3
        elif "7일" in text or "7day" in text:
            days = 7
        elif "1일" in text or "1day" in text or "오늘" in text:
            days = 1

        # Get jobs from last N days
        jobs_data = load_jobs_data()
        all_jobs = jobs_data.get("all_tracked_jobs", [])
        cutoff = datetime.now(datetime.timezone.utc) - timedelta(days=days)

        recent = [
            j for j in all_jobs
            if j.get("first_seen_at")
            and datetime.fromisoformat(j["first_seen_at"].replace("Z", "+00:00")) >= cutoff
            and j.get("qualifies")
        ]

        # Format result
        from utils.notifications import send_telegram_text
        if recent:
            msg = f"🔍 최근 {days}일 신규 공고 ({len(recent)}개)\n\n"
            for job in recent[:10]:  # top 10
                msg += f"• {job.get('title', '?')} - {job.get('company', '?')} ({job.get('match_score', 0)}점)\n"
            if len(recent) > 10:
                msg += f"\n... 외 {len(recent)-10}개"
            send_telegram_text(msg)
        else:
            send_telegram_text(f"최근 {days}일 신규 공고가 없습니다.")

        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
