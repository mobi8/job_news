#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from utils.config import OUTPUT_DIR


NOISY_MIN_PARSED = int(os.getenv("ROUTE_OBSERVABILITY_NOISY_MIN_PARSED", "25"))
NOISY_MAX_FILTER_RATE = float(os.getenv("ROUTE_OBSERVABILITY_NOISY_MAX_FILTER_RATE", "0.15"))


def new_run_id(prefix: str = "collection") -> str:
    stamp = datetime.now(timezone.utc).isoformat()
    return f"{stamp.replace(':', '').replace('-', '')}-{prefix}-{os.getpid()}"


def run_dir(run_id: str) -> Path:
    path = OUTPUT_DIR / "runs" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def classify_health(
    *,
    attempted: bool,
    status: str,
    parsed: int | None,
    raw: int | None = None,
    filtered: int | None = None,
    error: str | None = None,
) -> str:
    if not attempted:
        return "skipped"
    if error or status in {"failed", "timeout", "auth", "checkpoint", "parser_error", "malformed"}:
        return "failed"
    if status not in {"success", "partial"}:
        return "failed"
    parsed_count = int(parsed or 0)
    if parsed_count == 0:
        return "zero"
    if raw is not None and filtered is not None and int(raw or 0) >= NOISY_MIN_PARSED:
        filter_rate = float(filtered or 0) / max(1, int(raw or 0))
        if filter_rate <= NOISY_MAX_FILTER_RATE:
            return "noisy"
    return "healthy"


def append_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def _cell_status(record: dict[str, Any]) -> str:
    health = str(record.get("health") or "skipped")
    raw = record.get("raw")
    parsed = record.get("parsed")
    if health == "healthy":
        marker = "OK"
    elif health == "zero":
        marker = "ZERO"
    elif health == "noisy":
        marker = "NOISY"
    elif health == "failed":
        marker = "FAIL"
    else:
        marker = "SKIP"
    return f"{marker} r={raw if raw is not None else '-'} p={parsed if parsed is not None else '-'}"


def aggregate_location_role(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    rank = {"failed": 4, "noisy": 3, "zero": 2, "healthy": 1, "skipped": 0}
    for record in records:
        key = (str(record.get("location_id") or record.get("location") or ""), str(record.get("role_id") or ""))
        if key not in grouped:
            order.append(key)
            grouped[key] = {
                "location_id": key[0],
                "location": record.get("location"),
                "role_id": key[1],
                "attempted": False,
                "raw": None,
                "parsed": None,
                "filtered": None,
                "new": None,
                "elapsed_ms": None,
                "health": "skipped",
                "errors": [],
                "records": 0,
            }
        cell = grouped[key]
        cell["records"] += 1
        cell["attempted"] = bool(cell["attempted"] or record.get("attempted"))
        for metric in ("raw", "parsed", "filtered"):
            if record.get(metric) is not None:
                cell[metric] = int(cell.get(metric) or 0) + int(record.get(metric) or 0)
        if record.get("elapsed_ms") is not None:
            cell["elapsed_ms"] = int(cell.get("elapsed_ms") or 0) + int(record.get("elapsed_ms") or 0)
        if record.get("error"):
            cell["errors"].append(str(record.get("error")))
        health = str(record.get("health") or "skipped")
        if rank.get(health, 0) > rank.get(str(cell.get("health") or "skipped"), 0):
            cell["health"] = health
    return [grouped[key] for key in order]


def render_compact_telegram_summary(
    *,
    run_id: str,
    records: Iterable[dict[str, Any]],
    summary_path: Path,
    max_lines: int = 25,
) -> str:
    items = list(records)
    source_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    location_counts: dict[str, int] = defaultdict(int)
    failures: list[str] = []
    for record in items:
        source = str(record.get("source") or "unknown")
        health = str(record.get("health") or "skipped")
        source_counts[source][health] += 1
        if record.get("parsed") is not None:
            location_counts[str(record.get("location") or record.get("location_id") or "unknown")] += int(record.get("parsed") or 0)
        if health == "failed" and len(failures) < 3:
            err = str(record.get("error") or "failed").replace("\n", " ")[:90]
            failures.append(f"- {record.get('location_id')}/{record.get('role_id')}: {err}")

    lines = [f"Collection routes {run_id}", "Routing:"]
    for source, counts in sorted(source_counts.items()):
        parts = [f"{name}={counts[name]}" for name in ("healthy", "zero", "noisy", "failed", "skipped") if counts.get(name)]
        lines.append(f"- {source}: " + (", ".join(parts) if parts else "none"))
    lines.append("Parsed volume:")
    top_locations = sorted(location_counts.items(), key=lambda item: item[1], reverse=True)
    for location, count in top_locations[:5]:
        lines.append(f"- {location}: {count}")
    if len(top_locations) > 5:
        other_total = sum(count for _, count in top_locations[5:])
        lines.append(f"- Other {len(top_locations) - 5} locations: {other_total}")
    if failures:
        lines.append("Failed routes:")
        lines.extend(failures)
    lines.append(f"Details: {summary_path}")
    return "\n".join(lines[:max_lines])


def write_markdown_summary(path: Path, *, run_id: str, records: Iterable[dict[str, Any]]) -> None:
    items = list(records)
    jobs = [record for record in items if record.get("source") == "linkedin_jobs"]
    posts = [record for record in items if record.get("source") == "linkedin_posts"]
    lines = [
        f"# Route Summary {run_id}",
        "",
        "Unavailable per-route metrics are recorded as `null` when the current pipeline cannot accurately attribute them.",
        "",
    ]
    for title, subset in (("LinkedIn Jobs", jobs), ("LinkedIn Posts", posts)):
        cells = aggregate_location_role(subset)
        locations = sorted({str(cell.get("location_id") or "") for cell in cells})
        roles = sorted({str(cell.get("role_id") or "") for cell in cells})
        lines.extend([f"## {title}", ""])
        if not cells:
            lines.extend(["No records.", ""])
            continue
        lines.append("| Location | " + " | ".join(roles) + " |")
        lines.append("|---|" + "|".join("---" for _ in roles) + "|")
        by_key = {(str(cell.get("location_id") or ""), str(cell.get("role_id") or "")): cell for cell in cells}
        for location in locations:
            row = [location]
            for role in roles:
                row.append(_cell_status(by_key.get((location, role), {"health": "skipped"})))
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
