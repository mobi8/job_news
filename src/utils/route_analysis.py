#!/usr/bin/env python3
"""Route-level analysis and audit tools for collection efficiency.

Processes route observability data from multiple runs to identify patterns,
weaknesses, and optimization opportunities.

Usage:
  python -m src.utils.route_analysis --source linkedin_jobs --runs 5
  python -m src.utils.route_analysis --source linkedin_posts --runs 3 --output json
"""

import json
import logging
import sys
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RouteRecord:
    """Single route execution record."""
    source: str
    location: str
    role: str
    query: str
    status: str  # healthy, zero, failed
    raw_count: int
    parsed_count: int
    elapsed_seconds: float
    timestamp: str
    run_id: str
    error_message: Optional[str] = None


@dataclass
class RouteStats:
    """Aggregated statistics for a single route."""
    source: str
    location: str
    role: str
    query: str

    total_runs: int = 0
    healthy_runs: int = 0
    zero_runs: int = 0
    failed_runs: int = 0

    total_raw: int = 0
    total_parsed: int = 0
    avg_raw_per_run: float = 0.0
    avg_parsed_per_run: float = 0.0

    avg_elapsed_seconds: float = 0.0

    status_changes: List[str] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)

    classification: str = ""  # strong, healthy, weak, zero, failed, noisy
    recommendation: str = ""  # keep, retry, merge, narrow, broaden, disable


@dataclass
class AuditResult:
    """Complete audit result for a source."""
    source: str
    run_count: int
    timestamp: str

    total_routes: int = 0
    healthy_routes: int = 0
    zero_routes: int = 0
    failed_routes: int = 0

    total_raw_jobs: int = 0
    total_parsed_jobs: int = 0

    routes_by_classification: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    coverage_gaps: List[str] = field(default_factory=list)


class RouteAnalyzer:
    """Analyzes route-level collection data."""

    def __init__(self, source: str, runs: int = 5):
        self.source = source
        self.runs = runs
        self.routes: List[RouteRecord] = []
        self.stats: Dict[str, RouteStats] = {}

    def load_run_data(self, run_id: str) -> bool:
        """Load targets.jsonl from a specific run."""
        run_path = Path(f"outputs/runs/{run_id}/targets.jsonl")
        if not run_path.exists():
            logger.warning(f"Run data not found: {run_path}")
            return False

        try:
            with open(run_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("source") == self.source:
                            self.routes.append(RouteRecord(
                                source=record.get("source", ""),
                                location=record.get("location", ""),
                                role=record.get("role", ""),
                                query=record.get("query", ""),
                                status=record.get("status", "unknown"),
                                raw_count=record.get("raw_count", 0),
                                parsed_count=record.get("parsed_count", 0),
                                elapsed_seconds=record.get("elapsed_seconds", 0.0),
                                timestamp=record.get("timestamp", ""),
                                run_id=run_id,
                                error_message=record.get("error_message"),
                            ))
                    except json.JSONDecodeError:
                        continue
            return True
        except Exception as e:
            logger.error(f"Failed to load run data: {e}")
            return False

    def aggregate_stats(self) -> None:
        """Compute aggregated statistics per route."""
        route_data: Dict[str, List[RouteRecord]] = defaultdict(list)

        for record in self.routes:
            key = f"{record.location}|{record.role}|{record.query}"
            route_data[key].append(record)

        for key, records in route_data.items():
            location, role, query = key.split("|", 2)
            stats = RouteStats(
                source=self.source,
                location=location,
                role=role,
                query=query,
            )

            stats.total_runs = len(records)
            stats.healthy_runs = sum(1 for r in records if r.status == "healthy")
            stats.zero_runs = sum(1 for r in records if r.status == "zero")
            stats.failed_runs = sum(1 for r in records if r.status == "failed")

            stats.total_raw = sum(r.raw_count for r in records)
            stats.total_parsed = sum(r.parsed_count for r in records)

            if stats.healthy_runs > 0:
                healthy = [r for r in records if r.status == "healthy"]
                stats.avg_raw_per_run = sum(r.raw_count for r in healthy) / len(healthy)
                stats.avg_parsed_per_run = sum(r.parsed_count for r in healthy) / len(healthy)

            stats.avg_elapsed_seconds = sum(r.elapsed_seconds for r in records) / len(records)

            stats.status_changes = [r.status for r in sorted(records, key=lambda x: x.timestamp)]
            stats.error_messages = [r.error_message for r in records if r.error_message]

            self.classify_route(stats)
            self.stats[key] = stats

    def classify_route(self, stats: RouteStats) -> None:
        """Classify route health and performance."""
        if stats.failed_runs == stats.total_runs:
            stats.classification = "failed"
            stats.recommendation = "retry (network issues) or disable if persistent"
        elif stats.zero_runs == stats.total_runs:
            stats.classification = "zero"
            stats.recommendation = "investigate query, broaden, or disable"
        elif stats.healthy_runs >= stats.total_runs * 0.8:
            if stats.avg_parsed_per_run >= 50:
                stats.classification = "strong"
                stats.recommendation = "keep and monitor"
            elif stats.avg_parsed_per_run >= 10:
                stats.classification = "healthy"
                stats.recommendation = "keep"
            else:
                stats.classification = "weak"
                stats.recommendation = "narrow query or consider merging"
        else:
            stats.classification = "noisy"
            stats.recommendation = "investigate instability"

    def generate_audit(self) -> AuditResult:
        """Generate complete audit result."""
        result = AuditResult(
            source=self.source,
            run_count=self.runs,
            timestamp=datetime.now().isoformat(),
        )

        result.total_routes = len(self.stats)
        for stats in self.stats.values():
            result.total_raw_jobs += stats.total_raw
            result.total_parsed_jobs += stats.total_parsed

            if stats.classification == "healthy":
                result.healthy_routes += 1
            elif stats.classification == "zero":
                result.zero_routes += 1
            elif stats.classification == "failed":
                result.failed_routes += 1

        # Group by classification
        by_classification = defaultdict(list)
        for key, stats in self.stats.items():
            by_classification[stats.classification].append(asdict(stats))

        result.routes_by_classification = dict(by_classification)

        # Generate recommendations
        self._generate_recommendations(result)
        self._identify_coverage_gaps(result)

        return result

    def _generate_recommendations(self, result: AuditResult) -> None:
        """Generate actionable recommendations."""
        recommendations = []

        # Failed routes
        failed = result.routes_by_classification.get("failed", [])
        if failed:
            recommendations.append(f"CRITICAL: {len(failed)} routes consistently failed. Check network/query syntax.")

        # Always-zero routes
        zero = result.routes_by_classification.get("zero", [])
        if zero:
            for route in zero[:3]:  # Top 3
                recommendations.append(
                    f"Route {route['location']}/{route['role']} always zero - "
                    f"consider broadening query or disabling"
                )

        # Weak routes
        weak = result.routes_by_classification.get("weak", [])
        if weak:
            for route in weak[:2]:
                recommendations.append(
                    f"Route {route['location']}/{route['role']} weak (<10 jobs avg) - "
                    f"consider narrowing specialization or merging with related role"
                )

        # High variance (noisy)
        noisy = result.routes_by_classification.get("noisy", [])
        if noisy:
            for route in noisy[:2]:
                recommendations.append(
                    f"Route {route['location']}/{route['role']} unstable - "
                    f"investigate query timing or target availability"
                )

        result.recommendations = recommendations

    def _identify_coverage_gaps(self, result: AuditResult) -> None:
        """Identify missing domain/role combinations."""
        gaps = []

        if self.source == "linkedin_jobs":
            expected_roles = {"payments", "custody", "settlement", "product", "igaming"}
            expected_locations = {"uae", "amsterdam", "remote", "australia"}

            actual_roles = {s["role"] for s in self.stats.values()}
            actual_locations = {s["location"] for s in self.stats.values()}

            missing_roles = expected_roles - actual_roles
            missing_locations = expected_locations - actual_locations

            if missing_roles:
                gaps.append(f"Missing roles: {', '.join(missing_roles)}")
            if missing_locations:
                gaps.append(f"Missing locations: {', '.join(missing_locations)}")

        result.coverage_gaps = gaps

    def to_markdown(self) -> str:
        """Generate Markdown report."""
        audit = self.generate_audit()
        lines = []

        lines.append(f"# Route Audit: {self.source.upper()}\n")
        lines.append(f"**Generated:** {audit.timestamp}")
        lines.append(f"**Runs Analyzed:** {audit.run_count}\n")

        lines.append("## Summary\n")
        lines.append(f"- Total routes: {audit.total_routes}")
        lines.append(f"- Healthy: {audit.healthy_routes}")
        lines.append(f"- Zero: {audit.zero_routes}")
        lines.append(f"- Failed: {audit.failed_routes}")
        lines.append(f"- Total raw jobs: {audit.total_raw_jobs:,}")
        lines.append(f"- Total parsed jobs: {audit.total_parsed_jobs:,}\n")

        # Classification breakdown
        lines.append("## Routes by Classification\n")
        for classification in ["strong", "healthy", "weak", "zero", "failed", "noisy"]:
            routes = audit.routes_by_classification.get(classification, [])
            if routes:
                lines.append(f"### {classification.upper()} ({len(routes)} routes)\n")
                for route in sorted(routes, key=lambda r: -r["total_parsed"]):
                    lines.append(
                        f"- **{route['location']}/{route['role']}**: "
                        f"{route['total_parsed']} parsed (avg {route['avg_parsed_per_run']:.1f}/run), "
                        f"{route['healthy_runs']}/{route['total_runs']} healthy"
                    )
                lines.append("")

        # Recommendations
        if audit.recommendations:
            lines.append("## Recommendations\n")
            for rec in audit.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        # Coverage gaps
        if audit.coverage_gaps:
            lines.append("## Coverage Gaps\n")
            for gap in audit.coverage_gaps:
                lines.append(f"- {gap}")
            lines.append("")

        return "\n".join(lines)

    def to_json(self) -> Dict[str, Any]:
        """Generate JSON output."""
        audit = self.generate_audit()
        return asdict(audit)


def main():
    parser = ArgumentParser(description="Analyze collection route efficiency")
    parser.add_argument("--source", required=True, choices=["linkedin_jobs", "linkedin_posts"])
    parser.add_argument("--runs", type=int, default=5, help="Number of recent runs to analyze")
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    analyzer = RouteAnalyzer(args.source, args.runs)

    # Note: actual run loading would happen here once data exists
    analyzer.aggregate_stats()

    if args.output == "markdown":
        print(analyzer.to_markdown())
    else:
        print(json.dumps(analyzer.to_json(), indent=2))


if __name__ == "__main__":
    main()
