#!/usr/bin/env python3
"""Batch scrape job descriptions for LinkedIn and Indeed jobs with score >= 30"""

import json
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

def main():
    jobs_path = Path('outputs/jobs_analysis.json')
    if not jobs_path.exists():
        print("❌ jobs_analysis.json not found")
        sys.exit(1)

    data = json.loads(jobs_path.read_text(encoding='utf-8'))
    all_jobs = data.get('all_tracked_jobs', [])

    # Filter and sort by score
    linkedin_jobs = sorted(
        [j for j in all_jobs if j.get('source') == 'linkedin_public' and j.get('match_score', 0) >= 30],
        key=lambda x: x.get('match_score', 0),
        reverse=True
    )

    indeed_jobs = sorted(
        [j for j in all_jobs if j.get('source') == 'indeed_uae' and j.get('match_score', 0) >= 30],
        key=lambda x: x.get('match_score', 0),
        reverse=True
    )

    print(f"\n📊 배치 계획 (병렬 10개)")
    print(f"  LinkedIn: {len(linkedin_jobs)}개 중 100개 수집")
    print(f"  Indeed: {len(indeed_jobs)}개 중 100개 수집")
    print(f"  총 200개 job detail 스크래핑\n")

    linkedin_batch = linkedin_jobs[:100]
    indeed_batch = indeed_jobs[:100]

    def process_batch_parallel(batch, source_name):
        """Process a batch of jobs in parallel (10 at a time)"""
        results = {'source': source_name, 'success': 0, 'failed': 0, 'timeout': 0, 'jobs_map': {}}

        # Create mapping of url to job for later update
        jobs_map = {job.get('url', ''): job for job in batch if job.get('url', '')}

        def fetch_one_job(job_tuple):
            url, job = job_tuple
            title = job['title'][:50]
            score = job['match_score']
            old_len = len(job.get('description', ''))

            try:
                result = subprocess.run(
                    ['node', 'browser_probe.js', url],
                    capture_output=True,
                    text=True,
                    timeout=130
                )

                if result.returncode == 0:
                    try:
                        job_data = json.loads(result.stdout)
                        new_desc = job_data.get('description', '')[:5000]
                        return {'status': 'success', 'url': url, 'desc': new_desc, 'old_len': old_len, 'new_len': len(new_desc), 'title': title, 'score': score}
                    except json.JSONDecodeError:
                        return {'status': 'parse_error', 'url': url, 'title': title, 'score': score}
                else:
                    return {'status': 'error', 'url': url, 'title': title, 'score': score}
            except subprocess.TimeoutExpired:
                return {'status': 'timeout', 'url': url, 'title': title, 'score': score}
            except Exception as e:
                return {'status': 'exception', 'url': url, 'title': title, 'score': score, 'error': str(e)[:30]}

        # Process in parallel with 6 workers
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(fetch_one_job, (url, job)): i for i, (url, job) in enumerate(jobs_map.items(), 1)}

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    result = future.result()

                    if result['status'] == 'success':
                        jobs_map[result['url']]['description'] = result['desc']
                        results['success'] += 1
                        print(f"  [{idx:3}] ✓ {result['title']} ({result['score']}점) | {result['old_len']}→{result['new_len']}")
                    elif result['status'] == 'timeout':
                        results['timeout'] += 1
                        print(f"  [{idx:3}] ⏱ {result['title']} ({result['score']}점) | Timeout")
                    else:
                        results['failed'] += 1
                        print(f"  [{idx:3}] ✗ {result['title']} ({result['score']}점) | {result['status']}")
                except Exception as e:
                    results['failed'] += 1
                    print(f"  [{idx:3}] ✗ Error: {str(e)[:30]}")

        return results

    # Process LinkedIn
    print("🔵 LinkedIn 처리 중 (병렬 10개)...")
    linkedin_results = process_batch_parallel(linkedin_batch, 'linkedin_public')
    print(f"  ✅ 완료: {linkedin_results['success']}/100 성공\n")

    # Process Indeed
    print("🟠 Indeed 처리 중 (병렬 10개)...")
    indeed_results = process_batch_parallel(indeed_batch, 'indeed_uae')
    print(f"  ✅ 완료: {indeed_results['success']}/100 성공\n")

    # Save
    jobs_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # Summary
    total_success = linkedin_results['success'] + indeed_results['success']
    print("=" * 60)
    print(f"✅ 배치 완료: {total_success}/200 성공")
    print(f"   LinkedIn: {linkedin_results['success']}/100")
    print(f"   Indeed: {indeed_results['success']}/100")
    print(f"📁 저장: jobs_analysis.json")
    print("=" * 60)

if __name__ == '__main__':
    main()
