#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any, Dict, List

from .models import JobPosting
from .scoring import source_label
from .utils import dedupe_records_for_display, format_seen_timestamp, utc_now


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_csv(path: Path, jobs: List[JobPosting]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source",
                "title",
                "company",
                "location",
                "remote",
                "match_score",
                "first_seen_at",
                "url",
            ],
        )
        writer.writeheader()
        for job in jobs:
            writer.writerow(
                {
                    "source": job.source,
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "remote": job.remote,
                    "match_score": job.match_score,
                    "first_seen_at": job.first_seen_at,
                    "url": job.url,
                }
            )


def save_markdown(path: Path, stats: Dict[str, Any], jobs: List[JobPosting], inserted: int, sources: List[str]) -> None:
    lines = [
        "# UAE Job Watch Report",
        "",
        f"- Generated at: {utc_now().isoformat()}",
        f"- Sources: {', '.join(sources)}",
        f"- Total tracked jobs: {stats['total_jobs']}",
        f"- New this run: {inserted}",
        f"- New in last 7 days: {stats['new_last_7_days']}",
        "",
        "## Top Recommendations",
        "",
    ]

    for idx, job in enumerate(jobs, start=1):
        lines.extend(
            [
                f"### {idx}. {job.title}",
                f"- Source: {source_label(job.source)}",
                f"- Score: {job.match_score}",
                f"- Company: {job.company}",
                f"- Location: {job.location}",
                f"- First seen: {job.first_seen_at or 'N/A'}",
                f"- Link: {job.url}",
                "",
            ]
        )

    lines.extend(["## Top Locations", ""])
    for location, count in stats["top_locations"]:
        lines.append(f"- {location}: {count}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def save_dashboard(
    path: Path,
    stats: Dict[str, Any],
    source_total: List[Dict[str, Any]],
    source_daily: List[Dict[str, Any]],
    filtered_jobs: List[Dict[str, Any]],
    all_jobs: List[Dict[str, Any]],
    profile_loaded: bool,
) -> None:
    filtered_jobs = dedupe_records_for_display(filtered_jobs)
    all_jobs = dedupe_records_for_display(all_jobs)
    max_total = max((item["jobs"] for item in source_total), default=1)
    total_rows = []
    for item in source_total:
        width = max(8, int((item["jobs"] / max_total) * 100))
        total_rows.append(
            f"""
            <tr>
              <td>{source_label(item['source'])}</td>
              <td>{item['jobs']}</td>
              <td><div class="bar"><span style="width:{width}%"></span></div></td>
            </tr>
            """
        )

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in source_daily:
        grouped.setdefault(item["source"], []).append(item)

    daily_totals: Dict[str, int] = {}
    for item in source_daily:
        daily_totals[item["seen_date"]] = daily_totals.get(item["seen_date"], 0) + int(item["jobs"])
    trend_dates = sorted(daily_totals.keys())[-14:]
    trend_values = [daily_totals[day] for day in trend_dates]
    max_trend = max(trend_values, default=1)
    points = []
    if trend_values:
        width = 720
        height = 64
        for index, value in enumerate(trend_values):
            x = 20 + (index * (width - 40) / max(1, len(trend_values) - 1))
            y = 20 + ((max_trend - value) * (height - 40) / max(1, max_trend))
            points.append(f"{x:.1f},{y:.1f}")
    trend_polyline = " ".join(points)

    top_pick_cards = []
    for job in filtered_jobs[:6]:
        title = html.escape(job["title"])
        company = html.escape(job["company"])
        location = html.escape(job["location"])
        source = html.escape(source_label(job["source"]))
        url = html.escape(job["url"], quote=True)
        score = int(job.get("match_score", 0))
        seen = html.escape(format_seen_timestamp(job.get("first_seen_at", "")))
        top_pick_cards.append(
            f"""
            <a class="mini-job-card" href="{url}" target="_blank" rel="noreferrer">
              <div class="mini-job-top">
                <span class="summary-chip">{source}</span>
                <span class="summary-chip chip-yes">점수 {score}</span>
              </div>
              <div class="mini-job-title">{title}</div>
              <div class="mini-job-bottom">
                <div class="mini-job-meta">{company}</div>
                <div class="mini-job-meta">{location}</div>
                <div class="mini-job-meta">{seen}</div>
              </div>
            </a>
            """
        )

    recent_jobs = sorted(
        all_jobs,
        key=lambda item: item.get("first_seen_at") or "",
        reverse=True,
    )[:6]
    recent_cards = []
    for job in recent_jobs:
        title = html.escape(job["title"])
        company = html.escape(job["company"])
        location = html.escape(job["location"])
        source = html.escape(source_label(job["source"]))
        url = html.escape(job["url"], quote=True)
        seen = html.escape(format_seen_timestamp(job.get("first_seen_at", "")))
        recent_cards.append(
            f"""
            <a class="mini-job-card" href="{url}" target="_blank" rel="noreferrer">
              <div class="mini-job-top">
                <span class="summary-chip">{source}</span>
              </div>
              <div class="mini-job-title">{title}</div>
              <div class="mini-job-bottom">
                <div class="mini-job-meta">{company}</div>
                <div class="mini-job-meta">{location}</div>
                <div class="mini-job-meta">{seen}</div>
              </div>
            </a>
            """
        )

    all_rows = []
    for job in all_jobs[:500]:
        safe_title = html.escape(job["title"])
        safe_company = html.escape(job["company"])
        safe_source = html.escape(source_label(job["source"]))
        safe_location = html.escape(job["location"])
        safe_url = html.escape(job["url"], quote=True)
        safe_seen = html.escape(format_seen_timestamp(job.get("first_seen_at", "")))
        safe_seen_raw = html.escape(job.get("first_seen_at", ""), quote=True)
        safe_tags = html.escape(", ".join(job.get("fit_tags", [])))
        safe_key = html.escape(job["dashboard_key"], quote=True)
        safe_auto_category = html.escape(job.get("auto_category", ""), quote=True)
        qualifies_value = "Yes" if job.get("qualifies") else "No"
        meta_bits = [safe_company]
        if safe_location:
            meta_bits.append(safe_location)
        compact_meta = html.escape(" · ".join([job["company"], job["location"]]) if job.get("location") else job["company"])
        all_rows.append(
            f"""
            <tr class="job-row" data-source="{html.escape(job['source'], quote=True)}" data-recruiter="{'yes' if job.get('recruiter') else 'no'}" data-pass="{'yes' if job.get('qualifies') else 'no'}" data-auto-reject="{'yes' if job.get('auto_reject_exec') else 'no'}" data-tags="{safe_tags.lower()}" data-title="{safe_title.lower()}" data-company="{safe_company.lower()}" data-location="{safe_location.lower()}" data-seen-ts="{safe_seen_raw}">
              <td>
                <a href="{safe_url}" target="_blank" rel="noreferrer">{safe_title}</a>
                {"<div class=\"job-meta-line job-tags\">" + safe_tags + "</div>" if safe_tags else ""}
              </td>
              <td>
                <div class="job-meta-line" style="margin-top:0;color:var(--ink);">{safe_company}</div>
                <div class="job-meta-line">{safe_location or '-'}</div>
                <div style="margin-top:8px;">
                  <select class="compact-select" data-job-key="{safe_key}" data-field="category" data-default-category="{safe_auto_category}" aria-label="분류">
                    <option value="">분류</option>
                    <option value="crypto_product">Crypto Product</option>
                    <option value="payments">Payments</option>
                    <option value="casino">Casino / Sportsbook</option>
                    <option value="commercial">BD / Account / Sales</option>
                    <option value="recruiter">Recruiter-sourced</option>
                    <option value="compliance">Compliance / Regulation</option>
                    <option value="watchlist">Watchlist</option>
                  </select>
                </div>
              </td>
              <td>
                <div class="job-meta-line" style="margin-top:0;">{safe_seen}</div>
                <div class="summary-chip-row" style="margin-top:6px;">
                <span class="summary-chip">점수 {job.get("match_score", 0)}</span>
                <span class="summary-chip {"chip-yes" if qualifies_value == "Yes" else "chip-no"}">{"추천" if qualifies_value == "Yes" else "우선순위 낮음"}</span>
                </div>
                <div class="summary-chip-row" style="margin-top:6px;">
                <span class="summary-chip">{safe_source}</span>
                {"<span class=\"summary-chip\">헤드헌터</span>" if job.get("recruiter") else ""}
                </div>
              </td>
              <td>
                <div class="action-top-row">
                  <label class="inline-check"><input type="checkbox" data-job-key="{safe_key}" data-field="viewed"> 봤음</label>
                  <label class="inline-check"><input type="checkbox" data-job-key="{safe_key}" data-field="applied"> 지원함</label>
                  <label class="inline-check reject-inline"><input type="checkbox" data-job-key="{safe_key}" data-field="removed"> 제외</label>
                </div>
                <textarea data-job-key="{safe_key}" data-field="note" rows="2" placeholder="메모"></textarea>
              </td>
            </tr>
            """
        )

    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Job Watch Stats</title>
  <style>
    :root {{
      --bg: #f3f5f8;
      --bg-accent: #dde6f6;
      --card: #ffffff;
      --ink: #111827;
      --muted: #5f6b7a;
      --accent: #1d4ed8;
      --accent-soft: #dbe7ff;
      --line: rgba(17, 24, 39, 0.12);
      --pill: #e8eef9;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      color: var(--ink);
      background:
        linear-gradient(180deg, rgba(221, 230, 246, 0.65) 0%, rgba(221, 230, 246, 0) 140px),
        linear-gradient(180deg, #f8fbff 0%, var(--bg) 100%);
    }}
    .wrap {{
      max-width: 1340px;
      margin: 0 auto;
      padding: 16px 14px 30px;
    }}
    .hero {{
      padding: 12px 0 16px;
      background: transparent;
      border-bottom: 1px solid var(--line);
    }}
    h1, h2, h3 {{
      margin: 0 0 8px;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      letter-spacing: -0.045em;
    }}
    h1 {{
      font-size: 40px;
      line-height: 1;
    }}
    h2 {{
      font-size: 24px;
      line-height: 1.05;
    }}
    h3 {{
      font-size: 18px;
      line-height: 1.1;
    }}
    .meta {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-top: 20px;
    }}
    .runtime-panel {{
      margin-top: 16px;
      border: 0;
      border-radius: 0;
      padding: 0;
      background: transparent;
    }}
    .runtime-topline {{
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
      gap: 14px;
      align-items: start;
      margin-top: 10px;
    }}
    .runtime-last-meta {{
      margin-top: 6px;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}
    .runtime-last-meta strong {{
      display: block;
      color: var(--ink);
      font-size: 12px;
      margin-bottom: 2px;
    }}
    .overview-compact {{
      min-height: 0;
      padding: 12px 14px;
      border: 0;
      background: rgba(255, 255, 255, 0.72);
      min-height: 144px;
    }}
    .overview-summary {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}
    .overview-summary strong {{
      color: var(--ink);
      font-weight: 700;
    }}
    .overview-label {{
      display: block;
      margin-bottom: 3px;
      color: var(--ink);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .overview-value {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }}
    .runtime-box {{
      padding: 12px 14px;
      border: 0;
      background: rgba(255, 255, 255, 0.72);
      min-height: 144px;
    }}
    .runtime-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) 112px;
      gap: 10px;
      align-items: start;
      margin-top: 0;
    }}
    .runtime-button-row {{
      display: flex;
      gap: 8px;
      justify-content: flex-end;
      margin-top: 8px;
    }}
    .runtime-stat {{
      font-size: 13px;
      color: var(--muted);
      line-height: 1.4;
    }}
    .runtime-stat strong {{
      display: block;
      color: var(--ink);
      font-size: 12px;
      margin-bottom: 2px;
    }}
    .runtime-input {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 0;
      padding: 6px 8px;
      font: inherit;
      background: white;
      color: var(--ink);
      max-width: 120px;
    }}
    .runtime-actions {{
      display: contents;
    }}
    .action-btn {{
      border: 0;
      border-radius: 0;
      padding: 7px 10px;
      font: inherit;
      font-weight: 700;
      font-size: 13px;
      cursor: pointer;
      background: var(--accent);
      color: white;
    }}
    .action-btn.secondary {{
      background: var(--pill);
      color: var(--ink);
      border: 0;
    }}
    .trend-card {{
      margin-top: 18px;
      border: 0;
      border-radius: 0;
      padding: 10px 0 0;
      background: transparent;
      min-height: 0;
      border-top: 1px solid var(--line);
    }}
    .trend-svg {{
      width: 100%;
      height: auto;
      margin-top: 4px;
      display: block;
      opacity: 0.72;
    }}
    .trend-axis {{
      stroke: rgba(108, 129, 165, 0.14);
      stroke-width: 0.75;
    }}
    .trend-line {{
      fill: none;
      stroke: rgba(29, 78, 216, 0.55);
      stroke-width: 1.5;
      stroke-linecap: round;
      stroke-linejoin: round;
    }}
    .trend-dot {{
      fill: rgba(29, 78, 216, 0.45);
    }}
    .trend-labels {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-top: 4px;
      color: var(--muted);
      font-size: 11px;
    }}
    .spotlight-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-top: 8px;
    }}
    .mini-job-grid {{
      display: flex;
      flex-direction: column;
      gap: 0;
      margin-top: 10px;
    }}
    .filter-grid {{
      display: grid;
      grid-template-columns: 1.05fr repeat(4, minmax(136px, 0.92fr));
      gap: 8px;
      margin-top: 10px;
      align-items: center;
    }}
    .filter-check-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }}
    .section-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .section-toggle-row {{
      display: flex;
      justify-content: center;
      align-items: center;
      margin-top: 6px;
    }}
    .section-toggle {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 30px;
      height: 30px;
      padding: 0;
      border: 0;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      flex: 0 0 auto;
    }}
    .section-toggle:hover {{
      color: var(--ink);
    }}
    .section-toggle svg {{
      width: 16px;
      height: 16px;
      display: block;
    }}
    .filter-toggle svg {{
      width: 15px;
      height: 15px;
    }}
    .trend-toggle .trend-toggle-caret {{
      transition: transform 160ms ease;
    }}
    .trend-toggle[aria-expanded="false"] .trend-toggle-caret {{
      transform: rotate(0deg);
    }}
    .trend-toggle[aria-expanded="true"] .trend-toggle-caret {{
      transform: rotate(180deg);
    }}
    .toggle-panel[hidden] {{
      display: none !important;
    }}
    .filter-check {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      padding: 0 12px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255,255,255,0.9);
      color: var(--ink);
      font-size: 12px;
      font-weight: 600;
    }}
    .filter-check input {{
      width: 16px;
      height: 16px;
      margin: 0;
    }}
    .card {{
      background: transparent;
      border: 0;
      border-radius: 0;
      padding: 14px 0 0;
      box-shadow: none;
      margin-top: 14px;
      border-top: 1px solid var(--line);
    }}
    .tab-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .tab-btn {{
      border: 0;
      background: transparent;
      color: var(--ink);
      border-radius: 0;
      padding: 7px 2px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      border-bottom: 2px solid transparent;
    }}
    .tab-btn.is-active {{
      background: transparent;
      color: var(--accent);
      border-bottom-color: var(--accent);
      box-shadow: none;
    }}
    .tab-count {{
      margin-left: 8px;
      display: inline-flex;
      min-width: 20px;
      height: 20px;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      background: rgba(20, 93, 245, 0.08);
      color: inherit;
      font-size: 11px;
    }}
    .tab-btn.is-active .tab-count {{
      background: rgba(20, 93, 245, 0.12);
      color: var(--accent);
    }}
    .bucket-panel[hidden] {{
      display: none !important;
    }}
    .stat {{
      font-size: 38px;
      color: var(--accent);
      font-weight: 800;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
      font-size: 15px;
    }}
    th, td {{
      text-align: left;
      padding: 7px 6px;
      border-bottom: 1px solid var(--line);
      vertical-align: middle;
    }}
    .bar {{
      width: 100%;
      height: 10px;
      background: var(--accent-soft);
      border-radius: 999px;
      overflow: hidden;
    }}
    .bar span {{
      display: block;
      height: 100%;
      background: var(--accent);
      border-radius: 999px;
    }}
    .sections {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 18px;
      margin-top: 18px;
    }}
    .table-wrap {{
      width: 100%;
      overflow-x: auto;
      overflow-y: hidden;
      border-radius: 0;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
      overflow-wrap: anywhere;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .pill-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      background: var(--pill);
      color: var(--accent);
      border: 0;
      border-radius: 0;
      min-height: 26px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 700;
    }}
    .mini-job-card {{
      display: grid;
      grid-template-columns: 126px minmax(0, 1fr) 164px;
      gap: 8px;
      align-items: start;
      border: 0;
      border-radius: 0;
      padding: 8px 0;
      background: transparent;
      min-height: 0;
      height: auto;
      border-bottom: 1px solid var(--line);
    }}
    .mini-job-card:hover {{
      text-decoration: none;
      box-shadow: none;
    }}
    .mini-job-top {{
      display: flex;
      gap: 4px;
      flex-wrap: nowrap;
      margin-bottom: 0;
      align-self: start;
    }}
    .mini-job-title {{
      color: var(--ink);
      font-size: 13px;
      font-weight: 700;
      line-height: 1.16;
      letter-spacing: -0.03em;
      margin-bottom: 0;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .mini-job-meta {{
      color: var(--muted);
      font-size: 11px;
      line-height: 1.22;
      margin-top: 1px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .mini-job-bottom {{
      align-self: start;
      justify-self: end;
      text-align: right;
    }}
    select, textarea, input[type="checkbox"] {{
      font: inherit;
    }}
    select, textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 0;
      background: rgba(255, 255, 255, 0.92);
      padding: 7px 9px;
    }}
    .filter-grid input[type="search"] {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 0;
      background: rgba(255, 255, 255, 0.92);
      padding: 7px 9px;
      font: inherit;
    }}
    .filter-check {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border: 0;
      border-radius: 0;
      background: rgba(255, 255, 255, 0.92);
      min-height: 42px;
    }}
    .inline-check {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-size: 14px;
      white-space: nowrap;
    }}
    .reject-inline {{
      color: #b73d3d;
      font-weight: 700;
    }}
    .action-grid {{
      display: flex;
      gap: 14px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }}
    .action-top-row {{
      display: flex;
      gap: 12px;
      align-items: center;
      margin-bottom: 8px;
      flex-wrap: wrap;
    }}
    .action-select-grid {{
      display: grid;
      grid-template-columns: minmax(160px, 1fr) minmax(150px, 0.9fr);
      gap: 6px;
      align-items: center;
    }}
    .summary-chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 4px;
    }}
    .summary-chip {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 3px 8px;
      background: #eef4ff;
      color: #1f3e76;
      font-size: 10px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .chip-yes {{
      background: #e9f8ef;
      color: #1d7a46;
    }}
    .chip-no {{
      background: #fff1f1;
      color: #b73d3d;
    }}
    textarea {{
      width: 100%;
      min-width: 0;
      max-width: none;
      resize: vertical;
    }}
    th {{
      white-space: nowrap;
      position: sticky;
      top: 0;
      background: rgba(248, 251, 255, 0.98);
      z-index: 1;
      font-size: 14px;
      letter-spacing: -0.02em;
    }}
    td {{
      min-width: 80px;
      vertical-align: top;
    }}
    td:first-child {{
      min-width: 320px;
    }}
    td:nth-child(2) {{
      min-width: 280px;
    }}
    td:nth-child(3) {{
      min-width: 250px;
    }}
    td:nth-child(4) {{
      min-width: 380px;
    }}
    .status-board {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-top: 12px;
    }}
    .category-board {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-top: 12px;
    }}
    .status-card {{
      border: 0;
      border-radius: 0;
      padding: 14px;
      background: rgba(255,255,255,0.7);
    }}
    .status-card h3 {{
      margin-bottom: 6px;
    }}
    .status-count {{
      font-size: 28px;
      font-weight: 800;
      color: var(--accent);
      margin-bottom: 8px;
    }}
    .status-list {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      font-size: 13px;
      color: var(--muted);
    }}
    .category-card {{
      border: 0;
      border-radius: 0;
      padding: 14px;
      background: rgba(255,255,255,0.7);
    }}
    .row-muted {{
      opacity: 0.78;
    }}
    .filter-meta {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
    }}
    .job-meta-line {{
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.28;
    }}
    .column-chip {{
      display: inline-flex;
      margin-top: 0;
    }}
    .job-tags {{
      color: var(--accent);
    }}
    .compact-select {{
      margin-top: 0;
      margin-bottom: 0;
    }}
    .reject-hidden .reject-reason-select {{
      display: none;
    }}
    @media (max-width: 980px) {{
      .spotlight-grid {{
        grid-template-columns: 1fr;
      }}
      .runtime-topline {{
        grid-template-columns: 1fr;
      }}
      .runtime-box {{
        padding: 12px 14px;
      }}
      .runtime-grid {{
        grid-template-columns: 1fr;
      }}
      .runtime-button-row {{
        justify-content: flex-start;
        flex-wrap: wrap;
      }}
      .mini-job-card {{
        grid-template-columns: 1fr;
        gap: 8px;
      }}
      .mini-job-bottom {{
        justify-self: start;
        text-align: left;
      }}
      .filter-grid {{
        grid-template-columns: 1fr;
      }}
    }}
 </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <h1>Job Watch Stats</h1>
        <a href="/all-news.html" style="display:inline-flex;align-items:center;gap:8px;padding:10px 16px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:6px;color:#60a5fa;text-decoration:none;cursor:pointer;transition:all 0.2s;font-size:13px;font-weight:500;" onmouseover="this.style.background='rgba(255,255,255,0.08)';this.style.borderColor='#60a5fa';" onmouseout="this.style.background='rgba(255,255,255,0.05)';this.style.borderColor='rgba(255,255,255,0.1)';">News →</a>
      </div>
      <section class="runtime-panel">
        <h3>실행 상태</h3>
        <div class="runtime-topline">
          <div class="overview-compact">
            <div class="overview-summary">
              <strong>지역</strong> Dubai, UAE, Abu Dhabi, ADGM, Ras Al Khaimah 우선. Bahrain, Qatar, Saudi Arabia는 remote일 때만 포함.
              <br>
              <strong>도메인·직무</strong> Web3, digital asset, stablecoin, crypto payments, custody, game, gaming, casino, sportsbook 중심. Product, Product Owner, BD, Account Manager, Sales, Partnerships 우선.
              <br>
              <strong>프로필</strong> Resume: {"Loaded" if profile_loaded else "Inferred profile"} · Reject 누적 패턴, 오프라인·프레젠터·현장성 역할, 비적합 언어/기술 리더십 포지션 제외.
            </div>
          </div>
          <div class="runtime-box">
            <div class="runtime-grid">
              <label class="runtime-stat">
                <strong>자동 실행 주기(분)</strong>
                <input id="watch-interval-minutes" class="runtime-input" type="number" min="1" step="1" value="1440">
              </label>
            </div>
            <div class="runtime-button-row">
              <button id="save-watch-settings" class="action-btn secondary" type="button">설정 저장</button>
              <button id="run-scrape-now" class="action-btn" type="button">지금 실행</button>
            </div>
          </div>
        </div>
        <div class="runtime-last-meta">
          <strong>마지막 스크랩</strong>
          <div id="scrape-last-at">불러오는 중</div>
          <div id="scrape-last-ago">-</div>
        </div>
        <p id="runtime-status" class="meta" style="margin-top:10px;">현재 설정을 불러오는 중입니다.</p>
      </section>
      <section class="trend-card">
        <h2>일간 추이</h2>
        <p class="meta">최근 14일 기준 신규 공고 흐름입니다.</p>
        <div class="section-toggle-row">
          <button id="trend-toggle" class="section-toggle trend-toggle" type="button" aria-expanded="false" aria-controls="trend-panel" aria-label="일간 추이 접기/펼치기">
            <svg class="trend-toggle-caret" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M7 10l5 5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
            </svg>
          </button>
        </div>
        <div id="trend-panel" class="toggle-panel" hidden>
          <svg class="trend-svg" viewBox="0 0 720 64" preserveAspectRatio="none" aria-label="Daily trend">
            <line class="trend-axis" x1="20" y1="44" x2="700" y2="44"></line>
            <line class="trend-axis" x1="20" y1="20" x2="20" y2="44"></line>
            <polyline class="trend-line" points="{trend_polyline}"></polyline>
            {''.join(f'<circle class="trend-dot" cx="{20 + (index * (720 - 40) / max(1, len(trend_values) - 1)):.1f}" cy="{20 + ((max_trend - value) * (64 - 40) / max(1, max_trend)):.1f}" r="2.2"></circle>' for index, value in enumerate(trend_values))}
          </svg>
          <div class="trend-labels">
            <span>{html.escape(trend_dates[0]) if trend_dates else ''}</span>
            <span>총 추적 {stats['total_jobs']} · 24h {stats['new_last_1_day']} · 7d {stats['new_last_7_days']} · 30d {stats['new_last_30_days']}</span>
            <span>{html.escape(trend_dates[-1]) if trend_dates else ''}</span>
          </div>
        </div>
      </section>
    </section>

    <section class="card">
      <h2>빠른 보기</h2>
      <p class="meta">맨 위에서 바로 볼 만한 공고와 가장 최근 들어온 공고만 따로 모았습니다.</p>
      <div class="spotlight-grid">
        <div>
          <h3>추천</h3>
          <div class="mini-job-grid">
            {''.join(top_pick_cards)}
          </div>
        </div>
        <div>
          <h3>최신 등록</h3>
          <div class="mini-job-grid">
            {''.join(recent_cards)}
          </div>
        </div>
      </div>
    </section>

    <section class="card">
      <h2>보기 설정</h2>
      <p class="meta">정렬과 필터를 먼저 정한 뒤 아래 검토 보드에서 바로 처리하면 됩니다.</p>
      <div class="section-toggle-row">
        <button id="view-settings-toggle" class="section-toggle filter-toggle" type="button" aria-expanded="false" aria-controls="view-settings-panel" aria-label="보기 설정 접기/펼치기">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M3 5h18l-7 8v5l-4 2v-7L3 5z" fill="currentColor"></path>
          </svg>
        </button>
      </div>
      <div id="view-settings-panel" class="toggle-panel" hidden>
        <div class="filter-grid">
          <input id="filter-search" type="search" placeholder="공고명, 회사, 지역, 태그 검색">
          <select id="filter-sort">
            <option value="desc">최신순</option>
            <option value="asc">오래된순</option>
          </select>
          <select id="filter-source">
            <option value="">전체 출처</option>
            <option value="linkedin_public">LinkedIn</option>
            <option value="indeed_uae">Indeed UAE</option>
            <option value="jobvite_pragmaticplay">Jobvite</option>
            <option value="smartrecruitment">SmartRecruitment</option>
            <option value="igamingrecruitment">iGaming Recruitment</option>
            <option value="jobrapido_uae">Jobrapido</option>
            <option value="jobleads">JobLeads</option>
            <option value="telegram_job_crypto_uae">TG Jobs UAE</option>
            <option value="telegram_cryptojobslist">TG Crypto</option>
          </select>
          <select id="filter-track">
            <option value="">전체 분야</option>
            <option value="crypto">Crypto / Web3</option>
            <option value="payments">Payments / PSP / MTO</option>
            <option value="casino">Casino / Sportsbook / Live Casino</option>
            <option value="product">Product / Owner / Platform</option>
            <option value="commercial">BD / Account / Sales</option>
            <option value="regulation">ADGM / VARA / FSRA</option>
          </select>
          <select id="filter-status">
            <option value="">전체 상태</option>
            <option value="inbox">아직안본</option>
            <option value="applied">지원함</option>
            <option value="viewed">보류</option>
            <option value="rejected">제거함</option>
          </select>
        </div>
        <div class="filter-check-row">
          <label class="filter-check"><input id="filter-recruiter" type="checkbox"> 헤드헌터만</label>
          <label class="filter-check"><input id="filter-pass" type="checkbox"> 추천만</label>
          <label class="filter-check"><input id="filter-applied" type="checkbox"> 지원한 것만</label>
          <label class="filter-check"><input id="filter-show-removed" type="checkbox"> 제거한 것 보기</label>
        </div>
        <div id="filter-meta" class="filter-meta"></div>
      </div>
    </section>

    <section class="card">
      <h2>검토 보드</h2>
      <p class="meta">액션을 취하면 해당 탭으로 자동 이동합니다. 제거한 공고는 다음 수집 필터에도 반영됩니다.</p>
      <div class="tab-row">
        <button type="button" class="tab-btn is-active" data-tab-target="inbox">아직안본 <span id="tab-count-inbox" class="tab-count">0</span></button>
        <button type="button" class="tab-btn" data-tab-target="applied">지원한 <span id="tab-count-applied" class="tab-count">0</span></button>
        <button type="button" class="tab-btn" data-tab-target="viewed">보류 <span id="tab-count-viewed" class="tab-count">0</span></button>
        <button type="button" class="tab-btn" data-tab-target="rejected">제거함 <span id="tab-count-rejected" class="tab-count">0</span></button>
      </div>
    </section>

    <section class="card bucket-panel" data-tab-panel="inbox">
      <h2>아직안본 공고 <span id="bucket-count-inbox" class="summary-chip">0</span></h2>
      <p class="meta">아직 지원하지 않았고 제거하지 않은 공고입니다. 여기서 추천과 우선순위 낮음을 한 번 더 나눠 봅니다.</p>
      <div style="margin: 15px 0; padding: 12px; background: rgba(0,0,0,0.03); border-radius: 6px;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
          <label style="font-weight: 500; color: #4b5563; white-space: nowrap;">최소 스코어:</label>
          <input type="range" id="inbox-score-filter" min="0" max="100" value="50" style="flex: 1; cursor: pointer;">
          <span id="inbox-score-display" style="font-weight: 600; color: #3b82f6; min-width: 35px;">50</span>
        </div>
        <div style="font-size: 12px; color: #9ca3af;">
          <span id="inbox-filtered-count">0</span> / <span id="inbox-total-count">0</span> 공고
        </div>
      </div>
      <div class="tab-row" style="margin-top: 14px; margin-bottom: 10px;">
        <button type="button" class="tab-btn is-active" data-subtab-target="inbox-high">추천 <span id="bucket-count-inbox-high" class="tab-count">0</span></button>
        <button type="button" class="tab-btn" data-subtab-target="inbox-low">우선순위 낮음 <span id="bucket-count-inbox-low" class="tab-count">0</span></button>
      </div>
      <div data-subtab-panel="inbox-high" class="table-wrap">
        <table>
          <thead>
            <tr><th>공고</th><th>회사·지역</th><th>등록시각 · 점수 · 출처</th><th>관리</th></tr>
          </thead>
          <tbody id="bucket-inbox-high">
            {''.join(all_rows)}
          </tbody>
        </table>
      </div>
      <div data-subtab-panel="inbox-low" class="table-wrap" hidden>
        <table>
          <thead>
            <tr><th>공고</th><th>회사·지역</th><th>등록시각 · 점수 · 출처</th><th>관리</th></tr>
          </thead>
          <tbody id="bucket-inbox-low"></tbody>
        </table>
      </div>
    </section>

    <section class="card bucket-panel" data-tab-panel="applied" hidden>
      <h2>지원한 공고 <span id="bucket-count-applied" class="summary-chip">0</span></h2>
      <p class="meta">지원 완료, 인터뷰 진행, 오퍼 단계 공고를 모아둡니다.</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>공고</th><th>회사·지역</th><th>등록시각 · 점수 · 출처</th><th>관리</th></tr>
          </thead>
          <tbody id="bucket-applied"></tbody>
        </table>
      </div>
    </section>

    <section class="card bucket-panel" data-tab-panel="viewed" hidden>
      <h2>보류 공고 <span id="bucket-count-viewed" class="summary-chip">0</span></h2>
      <p class="meta">한 번 읽어봤거나 잠시 보관해두는 공고입니다.</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>공고</th><th>회사·지역</th><th>등록시각 · 점수 · 출처</th><th>관리</th></tr>
          </thead>
          <tbody id="bucket-viewed"></tbody>
        </table>
      </div>
    </section>

    <section class="card bucket-panel" data-tab-panel="rejected" hidden>
      <h2>제외한 공고 <span id="bucket-count-rejected" class="summary-chip">0</span></h2>
      <p class="meta">리젝트한 공고만 모아둡니다. 필요하면 다시 해제할 수 있습니다.</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>공고</th><th>회사·지역</th><th>등록시각 · 점수 · 출처</th><th>관리</th></tr>
          </thead>
          <tbody id="bucket-rejected"></tbody>
        </table>
      </div>
    </section>
  </div>
  <script>
    const rejectResetKey = "job_reject_reset_v1";
    const autoRejectExecKey = "job_auto_reject_exec_v1";
    const readState = (key) => {{
      try {{
        return JSON.parse(localStorage.getItem(`job_state:${{key}}`) || "{{}}");
      }} catch (error) {{
        return {{}};
      }}
    }};

    const writeState = (key, field, value) => {{
      const current = readState(key);
      current[field] = value;
      localStorage.setItem(`job_state:${{key}}`, JSON.stringify(current));
    }};

    const syncRejectFeedback = async () => {{
      const rejectedJobs = [];
      document.querySelectorAll("tbody tr").forEach((row) => {{
        const removed = row.querySelector('input[data-field="removed"]');
        if (!removed || !removed.checked) return;
        const noteEl = row.querySelector('textarea[data-field="note"]');
        const titleLink = row.querySelector("td a");
        rejectedJobs.push({{
          key: removed.dataset.jobKey || "",
          title: titleLink ? titleLink.textContent.trim() : "",
          company: row.dataset.company || "",
          location: row.dataset.location || "",
          source: row.dataset.source || "",
          remove_reason: "",
          note: noteEl ? noteEl.value : "",
        }});
      }});

      try {{
        await fetch("/reject-feedback", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ rejected_jobs: rejectedJobs, synced_at: new Date().toISOString() }}),
        }});
      }} catch (error) {{
      }}
    }};

    const clearRejectStateOnce = () => {{
      if (localStorage.getItem(rejectResetKey)) return;
      document.querySelectorAll("[data-job-key]").forEach((el) => {{
        const key = el.dataset.jobKey;
        const current = readState(key);
        if (current.removed || current.remove_reason) {{
          current.removed = false;
          delete current.remove_reason;
          localStorage.setItem(`job_state:${{key}}`, JSON.stringify(current));
        }}
      }});
      localStorage.setItem(rejectResetKey, "1");
    }};

    const applyAutoRejectExecOnce = () => {{
      if (localStorage.getItem(autoRejectExecKey)) return;
      document.querySelectorAll("tr[data-auto-reject='yes']").forEach((row) => {{
        const removed = row.querySelector('input[data-field="removed"]');
        const note = row.querySelector('textarea[data-field="note"]');
        const key = removed?.dataset.jobKey || note?.dataset.jobKey;
        if (!key) return;
        writeState(key, "removed", true);
        writeState(key, "viewed", false);
        writeState(key, "applied", false);
        if (!readState(key).note) {{
          writeState(key, "note", "CTO/engineering leadership role auto-rejected");
        }}
      }});
      localStorage.setItem(autoRejectExecKey, "1");
    }};

    const trackMatchers = {{
      crypto: ['crypto', 'web3', 'blockchain', 'digital assets', 'custody', 'stablecoin', 'wallet'],
      payments: ['payment', 'payments', 'psp', 'mto', 'settlement', 'fintech'],
      casino: ['casino', 'sportsbook', 'live casino', 'gaming platform', 'betting', 'igaming'],
      product: ['product', 'owner', 'platform', 'it product'],
      commercial: ['account manager', 'business development', 'sales', 'country manager', 'affiliate'],
      regulation: ['adgm', 'vara', 'vera', 'fsra', 'compliance', 'regulatory'],
    }};

    const categoryLabels = {{
      "": "Unsorted",
      crypto_product: "Crypto Product",
      payments: "Payments",
      casino: "Casino / Sportsbook",
      commercial: "BD / Account / Sales",
      recruiter: "Recruiter-sourced",
      compliance: "Compliance / Regulation",
      watchlist: "Watchlist",
    }};

    const syncRejectVisibility = () => {{
      document.querySelectorAll('.job-row input[data-field="removed"]').forEach((checkbox) => {{
        const row = checkbox.closest("tr");
        const actionCell = row ? row.children[3] : null;
        if (!actionCell) return;
        actionCell.classList.toggle("reject-hidden", !checkbox.checked);
      }});
    }};

    const formatHoursAgo = (isoValue) => {{
      if (!isoValue) return "-";
      const diffMs = Date.now() - Date.parse(isoValue);
      if (!Number.isFinite(diffMs)) return "-";
      const hours = diffMs / 3600000;
      if (hours < 1) return `${{Math.max(1, Math.round(diffMs / 60000))}}분 전`;
      return `${{hours.toFixed(1)}}시간 전`;
    }};

    const loadRuntimeState = async () => {{
      try {{
        const [settingsRes, stateRes] = await Promise.all([
          fetch("/watch-settings"),
          fetch("/scrape-state"),
        ]);
        const settings = await settingsRes.json();
        const state = await stateRes.json();
        document.getElementById("watch-interval-minutes").value = settings.scrape_interval_minutes || 1440;
        document.getElementById("scrape-last-at").textContent = state.last_scraped_at ? new Date(state.last_scraped_at).toLocaleString() : "아직 기록 없음";
        document.getElementById("scrape-last-ago").textContent = state.last_scraped_at ? `${{formatHoursAgo(state.last_scraped_at)}} · 마지막 모드 ${{state.mode || 'daily'}}` : "-";
        document.getElementById("runtime-status").textContent = "지금 실행은 수동 1회 스크랩이고, 완료되면 텔레그램 일일 요약도 같이 보냅니다. 자동 실행은 저장한 분 간격마다 1번씩 돌아갑니다.";
      }} catch (error) {{
        document.getElementById("runtime-status").textContent = "실행 상태를 불러오지 못했습니다.";
      }}
    }};

    const saveWatchSettings = async () => {{
      const interval = Number(document.getElementById("watch-interval-minutes").value || 1440);
      document.getElementById("runtime-status").textContent = "설정을 저장하는 중입니다...";
      try {{
        await fetch("/watch-settings", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            scrape_interval_minutes: interval,
          }}),
        }});
        document.getElementById("runtime-status").textContent = `자동 실행 주기를 ${{interval}}분으로 저장했습니다. 다음 사이클부터 반영됩니다.`;
      }} catch (error) {{
        document.getElementById("runtime-status").textContent = "설정 저장에 실패했습니다.";
      }}
    }};

    const pollForScrapeCompletion = async (previousLastScrapedAt) => {{
      const startedAt = Date.now();
      const timeoutMs = 10 * 60 * 1000;
      while (Date.now() - startedAt < timeoutMs) {{
        try {{
          const res = await fetch("/scrape-state");
          const state = await res.json();
          if (state.last_scraped_at && state.last_scraped_at !== previousLastScrapedAt) {{
            document.getElementById("scrape-last-at").textContent = new Date(state.last_scraped_at).toLocaleString();
            document.getElementById("scrape-last-ago").textContent = `${{formatHoursAgo(state.last_scraped_at)}} · 마지막 모드 ${{state.mode || 'daily'}}`;
            document.getElementById("runtime-status").textContent = "수동 실행이 완료됐습니다. 텔레그램 일일 요약 전송까지 포함된 사이클입니다.";
            return;
          }}
        }} catch (error) {{
          // ignore transient polling errors
        }}
        await new Promise((resolve) => setTimeout(resolve, 5000));
      }}
      document.getElementById("runtime-status").textContent = "수동 실행은 시작됐지만 완료 확인이 지연되고 있습니다. 조금 뒤 텔레그램이나 마지막 스크랩 시간을 확인해 주세요.";
    }};

    const runScrapeNow = async () => {{
      const previousLastScrapedAt = document.getElementById("scrape-last-at")?.textContent || "";
      document.getElementById("runtime-status").textContent = "수동 실행을 시작했습니다. 완료되면 텔레그램 일일 요약까지 같이 보냅니다.";
      try {{
        await fetch("/run-scrape", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ mode: "daily" }}),
        }});
        pollForScrapeCompletion(previousLastScrapedAt);
      }} catch (error) {{
        document.getElementById("runtime-status").textContent = "스크랩 시작에 실패했습니다.";
      }}
    }};

    const rowMatches = (row, bucketKey = "") => {{
      const searchValue = (document.getElementById("filter-search")?.value || "").trim().toLowerCase();
      const sourceValue = document.getElementById("filter-source")?.value || "";
      const trackValue = document.getElementById("filter-track")?.value || "";
      const statusValue = document.getElementById("filter-status")?.value || "";
      const recruiterOnly = Boolean(document.getElementById("filter-recruiter")?.checked);
      const passOnly = Boolean(document.getElementById("filter-pass")?.checked);
      const appliedOnly = Boolean(document.getElementById("filter-applied")?.checked);
      const showRemoved = Boolean(document.getElementById("filter-show-removed")?.checked);
      const inboxScoreMin = Number(document.getElementById("inbox-score-filter")?.value || 0);

      const textBlob = [
        row.dataset.title || "",
        row.dataset.company || "",
        row.dataset.location || "",
        row.dataset.tags || "",
      ].join(" ");
      if (searchValue && !textBlob.includes(searchValue)) return false;
      if (sourceValue && row.dataset.source !== sourceValue) return false;
      if (recruiterOnly && row.dataset.recruiter !== "yes") return false;
      if (passOnly && row.dataset.pass !== "yes") return false;

      const viewedCheckbox = row.querySelector('input[data-field="viewed"]');
      const checkbox = row.querySelector('input[data-field="applied"]');
      const removedCheckbox = row.querySelector('input[data-field="removed"]');
      const viewed = viewedCheckbox ? viewedCheckbox.checked : false;
      const applied = checkbox ? checkbox.checked : false;
      const removed = removedCheckbox ? removedCheckbox.checked : false;
      const bucket = rowBucket(row);

      if (appliedOnly && !applied) return false;
      if (!showRemoved && removed && bucketKey !== "rejected") return false;
      if (statusValue && statusValue !== bucket && !(statusValue === "inbox" && (bucket === "inbox_high" || bucket === "inbox_low"))) return false;
      if (trackValue) {{
        const keywords = trackMatchers[trackValue] || [];
        if (!keywords.some((keyword) => textBlob.includes(keyword))) return false;
      }}

      // inbox 섹션에서 스코어 필터 적용
      if ((bucket === "inbox_high" || bucket === "inbox_low") && !viewed && !applied && !removed) {{
        const score = Number(row.dataset.score || 0);
        if (score < inboxScoreMin) return false;
      }}

      return true;
    }};

    const rowBucket = (row) => {{
      const viewed = Boolean(row.querySelector('input[data-field="viewed"]')?.checked);
      const applied = Boolean(row.querySelector('input[data-field="applied"]')?.checked);
      const removed = Boolean(row.querySelector('input[data-field="removed"]')?.checked);
      const isPass = row.dataset.pass === "yes";

      if (removed) return "rejected";
      if (applied) return "applied";
      if (viewed) return "viewed";
      return isPass ? "inbox_high" : "inbox_low";
    }};

    const compareRows = (a, b) => {{
      const sortValue = document.getElementById("filter-sort")?.value || "desc";
      const aTs = Date.parse(a.dataset.seenTs || "") || 0;
      const bTs = Date.parse(b.dataset.seenTs || "") || 0;
      return sortValue === "asc" ? aTs - bTs : bTs - aTs;
    }};

    const updateBucketCounts = (counts) => {{
      const mapping = {{
        inbox: "bucket-count-inbox",
        inbox_high: "bucket-count-inbox-high",
        inbox_low: "bucket-count-inbox-low",
        applied: "bucket-count-applied",
        viewed: "bucket-count-viewed",
        rejected: "bucket-count-rejected",
      }};
      Object.entries(mapping).forEach(([key, id]) => {{
        const el = document.getElementById(id);
        if (el) el.textContent = String(counts[key] || 0);
        const tabEl = document.getElementById(id.replace("bucket-count", "tab-count"));
        if (tabEl) tabEl.textContent = String(counts[key] || 0);
      }});
    }};

    const setActiveTab = (tabKey) => {{
      document.querySelectorAll('[data-tab-target]').forEach((btn) => {{
        btn.classList.toggle('is-active', btn.dataset.tabTarget === tabKey);
      }});
      document.querySelectorAll('[data-tab-panel]').forEach((panel) => {{
        panel.hidden = panel.dataset.tabPanel !== tabKey;
      }});
    }};

    const bindCollapseToggle = (buttonId, panelId) => {{
      const button = document.getElementById(buttonId);
      const panel = document.getElementById(panelId);
      if (!button || !panel) return;
      button.addEventListener("click", () => {{
        const expanded = button.getAttribute("aria-expanded") === "true";
        button.setAttribute("aria-expanded", expanded ? "false" : "true");
        panel.hidden = expanded;
      }});
    }};

    const preserveScroll = (work) => {{
      const scrollX = window.scrollX;
      const scrollY = window.scrollY;
      work();
      requestAnimationFrame(() => {{
        window.scrollTo(scrollX, scrollY);
      }});
    }};

    const applyTableFilters = () => {{
      const rows = Array.from(document.querySelectorAll(".job-row"));
      const bucketBodies = {{
        inbox_high: document.getElementById("bucket-inbox-high"),
        inbox_low: document.getElementById("bucket-inbox-low"),
        applied: document.getElementById("bucket-applied"),
        viewed: document.getElementById("bucket-viewed"),
        rejected: document.getElementById("bucket-rejected"),
      }};
      const counts = {{ inbox: 0, inbox_high: 0, inbox_low: 0, applied: 0, viewed: 0, rejected: 0 }};
      rows.sort(compareRows).forEach((row) => {{
        const bucket = rowBucket(row);
        const matches = rowMatches(row, bucket);
        row.style.display = matches ? "" : "none";
        const body = bucketBodies[bucket];
        if (body) body.appendChild(row);
        if (matches) {{
          counts[bucket] += 1;
          if (bucket === "inbox_high" || bucket === "inbox_low") counts.inbox += 1;
        }}
      }});
      const meta = document.getElementById("filter-meta");
      if (meta) meta.textContent = `아직안본 ${{counts.inbox}} · 추천 ${{counts.inbox_high}} · 우선순위 낮음 ${{counts.inbox_low}} · 지원함 ${{counts.applied}} · 보류 ${{counts.viewed}} · 제거함 ${{counts.rejected}}`;
      updateBucketCounts(counts);
    }};

    clearRejectStateOnce();
    applyAutoRejectExecOnce();

    document.querySelectorAll("[data-job-key]").forEach((el) => {{
      const key = el.dataset.jobKey;
      const field = el.dataset.field;
      const state = readState(key);

      if (field === "viewed") {{
        el.checked = Boolean(state.viewed);
        el.addEventListener("change", () => {{
          writeState(key, "viewed", el.checked);
          preserveScroll(() => applyTableFilters());
        }});
      }} else if (field === "applied") {{
        el.checked = Boolean(state.applied);
        el.addEventListener("change", () => {{
          writeState(key, "applied", el.checked);
          preserveScroll(() => applyTableFilters());
          syncRejectFeedback();
        }});
      }} else if (field === "category") {{
        el.value = state.category || el.dataset.defaultCategory || "";
        el.addEventListener("change", () => {{
          writeState(key, "category", el.value);
        }});
      }} else if (field === "removed") {{
        el.checked = Boolean(state.removed);
        el.addEventListener("change", () => {{
          writeState(key, "removed", el.checked);
          preserveScroll(() => applyTableFilters());
          syncRejectVisibility();
          syncRejectFeedback();
        }});
      }} else if (field === "note") {{
        el.value = state.note || "";
        el.addEventListener("input", () => {{
          writeState(key, "note", el.value);
          syncRejectFeedback();
        }});
      }}
    }});
    ['filter-search','filter-sort','filter-source','filter-track','filter-status','filter-recruiter','filter-pass','filter-applied','filter-show-removed'].forEach((id) => {{
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener(id === 'filter-search' ? 'input' : 'change', applyTableFilters);
    }});

    // 스코어 게이지 필터 이벤트
    const scoreFilter = document.getElementById("inbox-score-filter");
    const scoreDisplay = document.getElementById("inbox-score-display");
    if (scoreFilter) {{
      scoreFilter.addEventListener("input", () => {{
        scoreDisplay.textContent = scoreFilter.value;
        updateInboxScoreStats();
        preserveScroll(() => applyTableFilters());
      }});
    }}

    // inbox 스코어 통계 업데이트
    const updateInboxScoreStats = () => {{
      const rows = Array.from(document.querySelectorAll(".job-row"));
      const inboxScoreMin = Number(document.getElementById("inbox-score-filter")?.value || 0);
      const inboxRows = rows.filter((row) => {{
        const bucket = rowBucket(row);
        const viewed = Boolean(row.querySelector('input[data-field="viewed"]')?.checked);
        const applied = Boolean(row.querySelector('input[data-field="applied"]')?.checked);
        const removed = Boolean(row.querySelector('input[data-field="removed"]')?.checked);
        return (bucket === "inbox_high" || bucket === "inbox_low") && !viewed && !applied && !removed;
      }});

      const filteredCount = inboxRows.filter((row) => {{
        const score = Number(row.dataset.score || 0);
        return score >= inboxScoreMin;
      }}).length;

      const totalCount = inboxRows.length;
      const filteredEl = document.getElementById("inbox-filtered-count");
      const totalEl = document.getElementById("inbox-total-count");
      if (filteredEl) filteredEl.textContent = String(filteredCount);
      if (totalEl) totalEl.textContent = String(totalCount);
    }};

    // 초기 통계 업데이트
    updateInboxScoreStats();
    const setSubActiveTab = (tabKey) => {{
      document.querySelectorAll('[data-subtab-target]').forEach((btn) => {{
        btn.classList.toggle('is-active', btn.dataset.subtabTarget === tabKey);
      }});
      document.querySelectorAll('[data-subtab-panel]').forEach((panel) => {{
        panel.hidden = panel.dataset.subtabPanel !== tabKey;
      }});
    }};

    document.querySelectorAll('[data-tab-target]').forEach((btn) => {{
      btn.addEventListener('click', () => setActiveTab(btn.dataset.tabTarget));
    }});

    document.querySelectorAll('[data-subtab-target]').forEach((btn) => {{
      btn.addEventListener('click', () => setSubActiveTab(btn.dataset.subtabTarget));
    }});
    document.getElementById("save-watch-settings")?.addEventListener("click", saveWatchSettings);
    document.getElementById("run-scrape-now")?.addEventListener("click", runScrapeNow);
    bindCollapseToggle("view-settings-toggle", "view-settings-panel");
    bindCollapseToggle("trend-toggle", "trend-panel");
    syncRejectVisibility();
    applyTableFilters();
    setActiveTab('inbox');
    syncRejectFeedback();
    loadRuntimeState();

    // 동적 통계 갱신: 페이지 로드 시 즉시 + 5분 간격
    async function fetchAndUpdateStats() {{
      try {{
        const data = await fetch('/job_stats_data.json').then(r => r.json());
        if (!data.filtered_jobs) return;
        const filteredJobs = data.filtered_jobs || [];

        // localStorage에서 job 상태 읽기
        const jobStatusMap = new Map();
        try {{
          const rawStatus = localStorage.getItem('job_status');
          if (rawStatus) {{
            const statusObj = JSON.parse(rawStatus);
            Object.entries(statusObj).forEach(([key, status]) => {{
              jobStatusMap.set(key, status);
            }});
          }}
        }} catch (e) {{
          console.warn('Failed to parse job status from localStorage:', e);
        }}

        const counts = {{
          inbox: filteredJobs.filter(j => {{
            const status = jobStatusMap.get(j.dashboard_key);
            return !status || (status !== 'applied' && status !== 'viewed' && status !== 'removed');
          }}).length,
          inbox_high: filteredJobs.filter(j => {{
            const status = jobStatusMap.get(j.dashboard_key);
            return (!status || (status !== 'applied' && status !== 'viewed' && status !== 'removed')) && j.match_score >= 75;
          }}).length,
          inbox_low: filteredJobs.filter(j => {{
            const status = jobStatusMap.get(j.dashboard_key);
            return (!status || (status !== 'applied' && status !== 'viewed' && status !== 'removed')) && j.match_score < 75;
          }}).length,
          applied: filteredJobs.filter(j => jobStatusMap.get(j.dashboard_key) === 'applied').length,
          viewed: filteredJobs.filter(j => jobStatusMap.get(j.dashboard_key) === 'viewed').length,
          rejected: filteredJobs.filter(j => jobStatusMap.get(j.dashboard_key) === 'removed').length,
        }};
        const mapping = {{
          inbox: 'bucket-count-inbox',
          inbox_high: 'bucket-count-inbox-high',
          inbox_low: 'bucket-count-inbox-low',
          applied: 'bucket-count-applied',
          viewed: 'bucket-count-viewed',
          rejected: 'bucket-count-rejected',
        }};
        Object.entries(mapping).forEach(([key, id]) => {{
          const el = document.getElementById(id);
          if (el) el.textContent = String(counts[key] || 0);
          const tabEl = document.getElementById(id.replace('bucket-count', 'tab-count'));
          if (tabEl) tabEl.textContent = String(counts[key] || 0);
        }});
      }} catch (e) {{
        console.error('Failed to fetch stats:', e);
      }}
    }}
    fetchAndUpdateStats();
    setInterval(fetchAndUpdateStats, 5 * 60 * 1000);
  </script>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")


def save_news_dashboard(path: Path) -> None:
    """Generate standalone news dashboard HTML with filters and pagination."""
    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>News Dashboard - Job Watch</title>
  <style>
    :root {{
      --bg: #0d1117;
      --surface: #161b22;
      --glass: rgba(255, 255, 255, 0.05);
      --accent: #60a5fa;
      --accent-dark: #3b82f6;
      --text-primary: #f0f6fc;
      --text-muted: #8b949e;
      --border: rgba(255, 255, 255, 0.1);
      --success: #3fb950;
      --error: #f85149;
    }}

    * {{
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }}

    html, body {{
      height: 100%;
      background-color: var(--bg);
      color: var(--text-primary);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
      font-size: 14px;
      line-height: 1.5;
    }}

    .wrap {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px;
    }}

    .page-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 30px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
    }}

    .page-header h1 {{
      font-size: 32px;
      font-weight: 700;
    }}

    .back-link {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 16px;
      background: var(--glass);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--accent);
      text-decoration: none;
      cursor: pointer;
      transition: all 0.2s;
      font-size: 13px;
      font-weight: 500;
    }}

    .back-link:hover {{
      background: rgba(255, 255, 255, 0.08);
      border-color: var(--accent);
    }}

    .filter-card {{
      background: var(--glass);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 20px;
      backdrop-filter: blur(10px);
    }}

    .filter-row {{
      display: grid;
      grid-template-columns: 1fr 220px auto;
      gap: 12px;
      margin-bottom: 16px;
    }}

    @media (max-width: 768px) {{
      .filter-row {{
        grid-template-columns: 1fr;
      }}
    }}

    .filter-row input,
    .filter-row select {{
      padding: 10px 12px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--text-primary);
      font-size: 13px;
      font-family: inherit;
    }}

    .filter-row input::placeholder {{
      color: var(--text-muted);
    }}

    .filter-row input:focus,
    .filter-row select:focus {{
      outline: none;
      border-color: var(--accent);
      background: rgba(96, 165, 250, 0.05);
    }}

    .filter-row button {{
      padding: 10px 18px;
      background: var(--accent);
      border: 0;
      border-radius: 6px;
      color: #0d1117;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      transition: background 0.2s;
    }}

    .filter-row button:hover {{
      background: var(--accent-dark);
    }}

    .stats-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
      color: var(--text-muted);
    }}

    .table-card {{
      background: var(--glass);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 20px;
      backdrop-filter: blur(10px);
      overflow-x: auto;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
    }}

    thead {{
      border-bottom: 2px solid var(--border);
    }}

    th {{
      padding: 12px 8px;
      text-align: left;
      font-weight: 600;
      color: var(--text-primary);
      font-size: 13px;
    }}

    tbody tr {{
      border-bottom: 1px solid var(--border);
      transition: background 0.2s;
    }}

    tbody tr:hover {{
      background: rgba(96, 165, 250, 0.05);
    }}

    td {{
      padding: 12px 8px;
      vertical-align: top;
      font-size: 13px;
    }}

    td a {{
      color: var(--accent);
      text-decoration: none;
      word-break: break-word;
    }}

    td a:hover {{
      text-decoration: underline;
    }}

    .loader {{
      text-align: center;
      padding: 40px;
      color: var(--text-muted);
    }}

    .error-msg {{
      padding: 16px;
      background: rgba(248, 81, 73, 0.1);
      border: 1px solid var(--error);
      border-radius: 6px;
      color: #ff7f7f;
      margin-bottom: 16px;
    }}

    #news-empty {{
      text-align: center;
      padding: 40px;
      color: var(--text-muted);
    }}

    .pagination {{
      display: flex;
      justify-content: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 20px;
    }}

    .pagination button {{
      padding: 8px 14px;
      background: var(--glass);
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--accent);
      cursor: pointer;
      font-size: 13px;
      transition: all 0.2s;
    }}

    .pagination button:hover:not(:disabled) {{
      background: rgba(96, 165, 250, 0.1);
      border-color: var(--accent);
    }}

    .pagination button.active {{
      background: var(--accent);
      color: var(--bg);
      border-color: var(--accent);
    }}

    .pagination button:disabled {{
      opacity: 0.5;
      cursor: not-allowed;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="page-header">
      <h1>📰 News Dashboard</h1>
      <a href="/job_stats_dashboard.html" class="back-link">← Job Board</a>
    </header>

    <section class="filter-card">
      <div class="filter-row">
        <input id="news-search" type="search" placeholder="기사 제목·내용·검색" >
        <select id="news-source">
          <option value="">전체 출처</option>
          <option value="rss_igaming_business">🎮 iGaming Business</option>
          <option value="rss_fintech_uae">💰 Fintech News UAE</option>
          <option value="rss_intergame_news">🎲 InterGame News</option>
          <option value="rss_intergame_crypto">₿ InterGame Crypto</option>
          <option value="rss_intergame_all">🎰 InterGame All</option>
          <option value="rss_intergame_abbrev">📰 InterGame Abbrev</option>
          <option value="rss_finextra_headlines">📈 FinExtra Headlines</option>
          <option value="rss_finextra_payments">💳 FinExtra Payments</option>
          <option value="rss_finextra_crypto">🔗 FinExtra Crypto</option>
          <option value="rss_player_pragmatic">👤 Player Feed</option>
        </select>
        <button id="search-btn">검색</button>
      </div>
      <div class="stats-row">
        <span id="news-stats-text">로딩 중...</span>
      </div>
    </section>

    <section class="table-card">
      <div id="news-loader" class="loader">로딩 중…</div>
      <div id="news-error" hidden class="error-msg"></div>
      <table id="news-table" style="display: none;">
        <thead>
          <tr>
            <th>제목</th>
            <th>출처</th>
            <th>날짜</th>
            <th>요약</th>
          </tr>
        </thead>
        <tbody id="news-body"></tbody>
      </table>
      <p id="news-empty" hidden>조건에 맞는 기사가 없습니다.</p>
    </section>

    <nav id="news-pagination" class="pagination"></nav>
  </div>

  <script>
    let currentPage = 1;
    const PAGE_SIZE = 20;
    let currentSource = '';
    let currentSearch = '';
    let totalArticles = 0;

    const formatDate = (val) => {{
      if (!val) return "-";
      try {{
        const parsed = new Date(val);
        if (isNaN(parsed)) return val.substring(0, 16);
        return parsed.toLocaleDateString("en-US", {{ month: "short", day: "numeric", year: "numeric" }});
      }} catch {{
        return val.substring(0, 16);
      }}
    }};

    async function loadNews(page = 1) {{
      const loader = document.getElementById('news-loader');
      const error = document.getElementById('news-error');
      const empty = document.getElementById('news-empty');
      const table = document.getElementById('news-table');
      const tbody = document.getElementById('news-body');
      const statsTxt = document.getElementById('news-stats-text');

      loader.hidden = false;
      error.hidden = true;
      empty.hidden = true;
      table.style.display = 'none';
      tbody.innerHTML = '';

      try {{
        const offset = (page - 1) * PAGE_SIZE;
        const params = new URLSearchParams({{ limit: PAGE_SIZE.toString(), offset: offset.toString() }});
        if (currentSource) params.set('source', currentSource);
        if (currentSearch) params.set('q', currentSearch);

        const response = await fetch(`/api/all-news?${{params.toString()}}`);
        if (!response.ok) throw new Error(`HTTP ${{response.status}}`);

        const data = await response.json();
        const articles = data.articles || [];
        totalArticles = data.total || 0;

        statsTxt.textContent = `총 ${{totalArticles}}건 · 페이지 ${{page}}/${{Math.ceil(totalArticles / PAGE_SIZE)}}`;

        if (!articles.length) {{
          empty.hidden = false;
          loader.hidden = true;
          return;
        }}

        articles.forEach(article => {{
          const row = document.createElement('tr');

          const titleCell = document.createElement('td');
          const link = document.createElement('a');
          link.href = article.url || '#';
          link.target = '_blank';
          link.rel = 'noreferrer';
          link.textContent = article.title || 'No title';
          titleCell.appendChild(link);

          const sourceCell = document.createElement('td');
          sourceCell.textContent = article.source_label || article.source || '-';

          const dateCell = document.createElement('td');
          dateCell.textContent = formatDate(article.published_at || article.date);

          const summaryCell = document.createElement('td');
          const summary = (article.summary || '').replace(/\\s+/g, ' ').trim();
          const truncated = summary.length > 100 ? summary.slice(0, 100) + '...' : summary;
          summaryCell.textContent = truncated;

          row.append(titleCell, sourceCell, dateCell, summaryCell);
          tbody.appendChild(row);
        }});

        table.style.display = 'table';
        renderPagination(totalArticles, page);
      }} catch (err) {{
        error.textContent = `오류: ${{err.message}}`;
        error.hidden = false;
      }} finally {{
        loader.hidden = true;
      }}
    }}

    function renderPagination(total, currentPageNum) {{
      const nav = document.getElementById('news-pagination');
      nav.innerHTML = '';

      const totalPages = Math.ceil(total / PAGE_SIZE);
      if (totalPages <= 1) return;

      // Previous button
      const prevBtn = document.createElement('button');
      prevBtn.textContent = '← 이전';
      prevBtn.disabled = currentPageNum === 1;
      prevBtn.addEventListener('click', () => {{
        if (currentPageNum > 1) loadNews(currentPageNum - 1);
      }});
      nav.appendChild(prevBtn);

      // Page numbers
      const startPage = Math.max(1, currentPageNum - 2);
      const endPage = Math.min(totalPages, currentPageNum + 2);

      for (let i = startPage; i <= endPage; i++) {{
        const btn = document.createElement('button');
        btn.textContent = i.toString();
        btn.className = i === currentPageNum ? 'active' : '';
        btn.addEventListener('click', () => loadNews(i));
        nav.appendChild(btn);
      }}

      // Next button
      const nextBtn = document.createElement('button');
      nextBtn.textContent = '다음 →';
      nextBtn.disabled = currentPageNum === totalPages;
      nextBtn.addEventListener('click', () => {{
        if (currentPageNum < totalPages) loadNews(currentPageNum + 1);
      }});
      nav.appendChild(nextBtn);
    }}

    // Event listeners
    document.getElementById('search-btn').addEventListener('click', () => {{
      currentSearch = document.getElementById('news-search').value.trim();
      currentSource = document.getElementById('news-source').value;
      currentPage = 1;
      loadNews(1);
    }});

    document.getElementById('news-search').addEventListener('keydown', (e) => {{
      if (e.key === 'Enter') document.getElementById('search-btn').click();
    }});

    document.getElementById('news-source').addEventListener('change', () => {{
      currentSource = document.getElementById('news-source').value;
      currentSearch = document.getElementById('news-search').value.trim();
      currentPage = 1;
      loadNews(1);
    }});

    // Initial load
    loadNews(1);
  </script>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")


def save_dashboard_data(
    data_path: Path,
    stats: Dict[str, Any],
    source_total: List[Dict[str, Any]],
    source_daily: List[Dict[str, Any]],
    filtered_jobs: List[Dict[str, Any]],
    all_jobs: List[Dict[str, Any]],
) -> None:
    """Save dashboard data as JSON only (HTML template remains unchanged)."""
    import json

    filtered_jobs = dedupe_records_for_display(filtered_jobs)
    all_jobs = dedupe_records_for_display(all_jobs)

    # Prepare data for JSON
    dashboard_data = {
        "stats": stats,
        "source_total": source_total,
        "source_daily": source_daily,
        "filtered_jobs": filtered_jobs,
        "all_jobs": all_jobs,
        "updated_at": utc_now().isoformat(),
    }

    data_path.parent.mkdir(parents=True, exist_ok=True)
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(dashboard_data, f, ensure_ascii=False, indent=2)
