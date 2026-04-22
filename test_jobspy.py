#!/usr/bin/env python3
"""Test JobSpy with LinkedIn scraping (proxy support for rate limiting)"""

import sys
sys.path.insert(0, '/Users/lewis/Desktop/agent/jobspy_env/lib/python3.11/site-packages')

from jobspy import scrape_jobs

# Test 1: With proxies for rate limiting
print("=" * 60)
print("Testing JobSpy: LinkedIn with proxy support")
print("=" * 60)

# Public proxies to test with (may or may not work, but tests the feature)
test_proxies = [
    "http://proxy.example.com:8080",  # Placeholder - will likely fail
]

jobs = scrape_jobs(
    site_name=["linkedin"],
    search_term="operations",
    location="Dubai",
    results_wanted=20,
    hours_old=168,
    verbose=1,
    linkedin_fetch_description=True,
    proxies=test_proxies,  # Test proxy support
)

print(f"\n✓ Found {len(jobs)} jobs")
if len(jobs) > 0:
    print("\nSample job:")
    job = jobs.iloc[0]
    print(f"  Title: {job['title']}")
    print(f"  Company: {job['company']}")
    print(f"  Site: {job['site']}")
    print(f"  Description length: {len(str(job.get('description', ''))) if job.get('description') else 0} chars")
    print(f"  URL: {job['job_url']}")

# Save to CSV
jobs.to_csv("/Users/lewis/Desktop/agent/outputs/jobspy_test.csv", index=False)
print(f"\n✓ Saved to outputs/jobspy_test.csv")
