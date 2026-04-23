#!/usr/bin/env python3
"""Quick test for float/NaN handling in JobSpy data."""
import sys
import os
sys.path.insert(0, '/Users/lewis/Desktop/agent')
os.chdir('/Users/lewis/Desktop/agent')

from src.watch.scraper import scrape_linkedin_indeed_via_jobspy
from src.utils.scoring import is_hard_excluded_job
from datetime import datetime, timedelta

print("Testing JobSpy data with nullable company field...")

try:
    # Test with just 1 keyword - modify scraper to test
    print("\n1. Scraping LinkedIn/Indeed with 1 keyword (crypto)...")
    from jobspy import scrape_jobs
    import pandas as pd

    linkedin_df = scrape_jobs(
        site_name=["linkedin"],
        search_term="crypto",
        location="Dubai",
        results_wanted=3,
        linkedin_fetch_description=True,
        verbose=0,
    )

    print(f"   Got {len(linkedin_df)} LinkedIn jobs")

    print("\n2. Checking company field types...")
    for idx, (_, row) in enumerate(linkedin_df.iterrows()):
        company = row['company']
        title = row['title']
        print(f"   Job {idx}: company={repr(company)} (type={type(company).__name__})")

        print(f"   Testing is_hard_excluded_job({repr(title[:30])}, {repr(company)})...")
        try:
            excluded = is_hard_excluded_job(
                title,
                company or None,
                row['location'] or "Dubai, UAE",
                row.get('description', "") or ""
            )
            print(f"   ✓ Passed (excluded={excluded})")
        except Exception as e:
            print(f"   ✗ FAILED: {e}")
            raise

    print("\n✓ All tests passed!")

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
