from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"{path.name} not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse {path.name}: {exc}")


@lru_cache(maxsize=1)
def load_jobs_data() -> Dict[str, Any]:
    return read_json(JOBS_DATA_PATH)


@lru_cache(maxsize=1)
def load_stats_data() -> Dict[str, Any]:
    return read_json(STATS_DATA_PATH)


def detect_country(job: Dict[str, Any]) -> str:
    location = (job.get("location") or "").lower()
    if "malta" in location or "valletta" in location:
        return "Malta"
    if "georgia" in location or "tbilisi" in location or "batumi" in location:
        return "Georgia"
    if "dubai" in location or "united arab emirates" in location or "uae" in location:
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
        "collection_metadata": jobs_data.get("collection_metadata"),
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
        "collection_metadata": data.get("collection_metadata"),
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
        "collection_metadata": stats.get("collection_metadata"),
    }


@app.get("/api/topics", summary="News topics")
def get_topics() -> Dict[str, Any]:
    stats = load_stats_data()
    return {"topics": stats.get("topics", [])}


@app.get("/api/player-mentions", summary="Player mentions")
def get_player_mentions() -> Dict[str, Any]:
    stats = load_stats_data()
    return {"player_mentions": stats.get("player_mentions", {})}


@app.get("/healthz")
def health_check() -> JSONResponse:
    if not JOBS_DATA_PATH.exists() or not STATS_DATA_PATH.exists():
        return JSONResponse(status_code=503, content={"status": "missing data files"})
    return JSONResponse(status_code=200, content={"status": "ok"})
