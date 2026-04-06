#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RSS 피드 테스트 스크립트
"""

import sys
from pathlib import Path

# Add src/ to path
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.scrapers import fetch_rss_news
from src.utils.config import NEWS_RSS_FEEDS

def test_rss_feed(feed_url: str, source: str, label: str) -> None:
    """RSS 피드 테스트"""
    print(f"\n🔍 테스트 중: {label}")
    print(f"   URL: {feed_url}")
    print(f"   소스: {source}")
    
    try:
        items = fetch_rss_news(feed_url, source)
        print(f"   ✅ 성공: {len(items)}개 아이템 수집")
        
        if items:
            for i, item in enumerate(items[:2]):  # 처음 2개만 출력
                print(f"     {i+1}. {item.title[:50]}...")
                print(f"        URL: {item.url[:80]}...")
                print(f"        날짜: {item.published_at[:19]}")
        else:
            print("     ⚠️  아이템 없음")
            
    except Exception as e:
        print(f"   ❌ 실패: {e}")

def main() -> None:
    print("📰 RSS 피드 테스트 시작")
    print("=" * 60)
    
    for feed in NEWS_RSS_FEEDS:
        test_rss_feed(feed["url"], feed["source"], feed["label"])
    
    print("\n" + "=" * 60)
    print("✅ 모든 RSS 피드 테스트 완료")

if __name__ == "__main__":
    main()