#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Queue exporter: exports high-scoring jobs (score >= 60) to career-ops queue file"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import Database
from utils.logger import watch_logger


# Queue file path for career-ops to read
QUEUE_FILE_PATH = Path("/Users/lewis/Desktop/career/career-ops/data/job_queue.jsonl")
MIN_SCORE_THRESHOLD = 60


def ensure_queue_directory() -> None:
    """Create queue directory if it doesn't exist"""
    QUEUE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)


def export_high_scoring_jobs(db_path: str, min_score: int = MIN_SCORE_THRESHOLD) -> Dict[str, Any]:
    """
    Export jobs with score >= min_score to JSONL queue file.

    Args:
        db_path: Path to jobs.sqlite3 database
        min_score: Minimum score threshold (default: 60)

    Returns:
        Dict with export statistics (count, file_path, exported_ids)
    """
    ensure_queue_directory()

    db = Database(Path(db_path))
    conn = db.conn
    cursor = conn.cursor()

    try:
        # Query jobs with score >= min_score, ordered by score DESC
        cursor.execute(
            """
            SELECT
                fingerprint as id,
                company,
                title as role,
                match_score as score,
                description,
                url,
                source,
                first_seen_at as collected_at
            FROM jobs
            WHERE match_score >= ?
            ORDER BY match_score DESC, first_seen_at DESC
            """,
            (min_score,),
        )

        rows = cursor.fetchall()
        if not rows:
            watch_logger.info(f"No jobs found with score >= {min_score}")
            return {
                "count": 0,
                "file_path": str(QUEUE_FILE_PATH),
                "exported_ids": [],
                "status": "no_jobs",
            }

        # Convert rows to dicts and append to JSONL file
        exported_ids = []
        with open(QUEUE_FILE_PATH, "a", encoding="utf-8") as f:
            for row in rows:
                job_dict = {
                    "id": row[0],
                    "company": row[1],
                    "role": row[2],
                    "score": row[3],
                    "description": row[4],
                    "url": row[5],
                    "source": row[6],
                    "collected_at": row[7],
                    "exported_at": datetime.utcnow().isoformat() + "Z",
                }
                f.write(json.dumps(job_dict, ensure_ascii=False) + "\n")
                exported_ids.append(job_dict["id"])

        watch_logger.info(
            f"Exported {len(exported_ids)} jobs with score >= {min_score} to {QUEUE_FILE_PATH}"
        )

        return {
            "count": len(exported_ids),
            "file_path": str(QUEUE_FILE_PATH),
            "exported_ids": exported_ids,
            "status": "success",
        }
    finally:
        cursor.close()
        conn.close()


def read_queue(queue_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Read queue file and return all jobs.

    Args:
        queue_path: Path to queue file (default: QUEUE_FILE_PATH)

    Returns:
        List of job dicts from queue file
    """
    path = Path(queue_path or QUEUE_FILE_PATH)
    if not path.exists():
        return []

    jobs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    jobs.append(json.loads(line))
                except json.JSONDecodeError:
                    watch_logger.warning(f"Failed to parse queue line: {line[:100]}")
                    continue

    return jobs


def clear_queue(queue_path: Optional[str] = None) -> None:
    """Clear queue file (use with caution)"""
    path = Path(queue_path or QUEUE_FILE_PATH)
    if path.exists():
        path.unlink()
        watch_logger.info(f"Cleared queue file: {path}")


def get_queue_stats(queue_path: Optional[str] = None) -> Dict[str, Any]:
    """Get statistics about current queue"""
    jobs = read_queue(queue_path)
    if not jobs:
        return {
            "count": 0,
            "file_path": str(QUEUE_FILE_PATH),
            "avg_score": 0,
            "min_score": 0,
            "max_score": 0,
        }

    scores = [job.get("score", 0) for job in jobs]
    return {
        "count": len(jobs),
        "file_path": str(QUEUE_FILE_PATH),
        "avg_score": sum(scores) / len(scores) if scores else 0,
        "min_score": min(scores) if scores else 0,
        "max_score": max(scores) if scores else 0,
    }


if __name__ == "__main__":
    # For manual testing
    db_path = "/Users/lewis/Desktop/agent/outputs/jobs.sqlite3"
    result = export_high_scoring_jobs(db_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Show queue stats
    stats = get_queue_stats()
    print("\nQueue Stats:")
    print(json.dumps(stats, indent=2, ensure_ascii=False))
