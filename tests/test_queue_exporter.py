#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for queue_exporter module"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.queue_exporter import export_high_scoring_jobs, read_queue, get_queue_stats, clear_queue


def test_queue_exporter():
    """Test basic queue export functionality"""
    db_path = "/Users/lewis/Desktop/agent/outputs/jobs.sqlite3"

    # Export high-scoring jobs
    print("Testing export_high_scoring_jobs...")
    result = export_high_scoring_jobs(db_path, min_score=60)
    print(f"  Count: {result['count']}")
    print(f"  Status: {result['status']}")
    assert result["status"] == "success"
    assert result["count"] > 0, "Should have at least 1 job with score >= 60"

    # Read queue
    print("\nTesting read_queue...")
    jobs = read_queue(result["file_path"])
    print(f"  Read {len(jobs)} jobs from queue")
    assert len(jobs) > 0, "Queue should have jobs"
    assert "id" in jobs[0], "Job should have id"
    assert "company" in jobs[0], "Job should have company"
    assert "role" in jobs[0], "Job should have role"
    assert "score" in jobs[0], "Job should have score"
    assert jobs[0]["score"] >= 60, "All jobs should have score >= 60"

    # Get stats
    print("\nTesting get_queue_stats...")
    stats = get_queue_stats(result["file_path"])
    print(f"  Queue count: {stats['count']}")
    print(f"  Avg score: {stats['avg_score']:.1f}")
    print(f"  Score range: {stats['min_score']}-{stats['max_score']}")
    assert stats["count"] >= len(jobs), "Stats count should match"

    # Verify JSONL format
    print("\nVerifying JSONL format...")
    with open(result["file_path"], "r", encoding="utf-8") as f:
        line_count = 0
        for line in f:
            if line.strip():
                json.loads(line)  # Should not raise
                line_count += 1
    print(f"  Valid JSONL with {line_count} lines")

    print("\n✅ All tests passed!")


if __name__ == "__main__":
    test_queue_exporter()
