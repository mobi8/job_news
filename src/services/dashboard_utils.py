#!/usr/bin/env python3

"""
대시보드 유틸리티 함수들
"""

import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse, parse_qs

def load_json(path: Path, default):
    """JSON 파일 로드"""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def send_json_response(handler, payload):
    """JSON 응답 보내기"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

def get_all_news_articles(path, db_path):
    """모든 뉴스 기사 조회"""
    if not db_path.exists():
        return {"articles": [], "total": 0, "sources": {}}
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 쿼리 파라미터 처리
    parsed_url = urlparse(path)
    query_params = parse_qs(parsed_url.query)
    source_filter = query_params.get('source', [None])[0]
    search_query = query_params.get('q', [None])[0]
    limit = int(query_params.get('limit', ['50'])[0])
    offset = int(query_params.get('offset', ['0'])[0])
    
    # 소스 라벨 매핑
    source_mapping = {
        "rss_igaming_business": "🎮 iGaming Business",
        "rss_fintech_uae": "💰 Fintech UAE",
        "rss_intergame_news": "🎲 InterGame News",
        "rss_intergame_crypto": "₿ InterGame Crypto",
        "rss_intergame_all": "🎰 InterGame All",
        "rss_intergame_abbrev": "📰 InterGame Abbrev",
        "rss_finextra_headlines": "📈 FinExtra Headlines",
        "rss_finextra_payments": "💳 FinExtra Payments",
        "rss_finextra_crypto": "🔗 FinExtra Crypto",
        "rss_player_pragmatic": "👤 Player Feed"
    }
    
    # 기본 쿼리
    query = "SELECT fingerprint, source, title, url, published_at, summary FROM news WHERE 1=1"
    params = []
    
    # 소스 필터
    if source_filter:
        query += " AND source = ?"
        params.append(source_filter)
    
    # 검색어 필터
    if search_query:
        query += " AND (title LIKE ? OR summary LIKE ?)"
        params.append(f"%{search_query}%")
        params.append(f"%{search_query}%")
    
    # 정렬 및 제한
    query += " ORDER BY published_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    articles = []
    for row in cursor.fetchall():
        fingerprint, source, title, url, published_at, summary = row
        articles.append({
            "fingerprint": fingerprint,
            "source": source,
            "source_label": source_mapping.get(source, source),
            "title": title,
            "url": url,
            "published_at": published_at,
            "summary": summary,
            "date": published_at[:10] if published_at else ""
        })
    
    # 총 개수 쿼리
    count_query = "SELECT COUNT(*) FROM news WHERE 1=1"
    count_params = []
    
    if source_filter:
        count_query += " AND source = ?"
        count_params.append(source_filter)
    if search_query:
        count_query += " AND (title LIKE ? OR summary LIKE ?)"
        count_params.append(f"%{search_query}%")
        count_params.append(f"%{search_query}%")
    
    cursor.execute(count_query, count_params)
    total_count = cursor.fetchone()[0]
    
    # 소스별 통계
    stats_query = "SELECT source, COUNT(*) as count FROM news GROUP BY source ORDER BY count DESC"
    cursor.execute(stats_query)
    source_stats = {}
    for source, count in cursor.fetchall():
        source_stats[source_mapping.get(source, source)] = count
    
    conn.close()
    
    return {
        "articles": articles,
        "total": total_count,
        "page_size": limit,
        "offset": offset,
        "source_stats": source_stats,
        "sources": list(source_mapping.values())
    }

def render_dashboard_html(html_path, output_dir):
    """대시보드 HTML 렌더링"""
    html_content = html_path.read_text(encoding="utf-8")
    
    # 간단한 상태 정보 추가
    try:
        scrape_state = load_json(output_dir / "scrape_state.json", {})
        mode = scrape_state.get("mode", "—")
        last_at = scrape_state.get("last_scraped_at", "")
        new_jobs = scrape_state.get("new_jobs_this_run", 0)
        
        status_html = f'''
            <div style="margin: 10px 0; padding: 10px; background: rgba(0,0,0,0.05); border-radius: 6px; font-size: 12px;">
                <strong>배치 상태:</strong> {mode} 모드 · 신규 {new_jobs}건 · 마지막: {last_at[:16] if last_at else "—"}
            </div>
        '''
        
        # hero 섹션 뒤에 추가
        if '<section class="hero">' in html_content:
            hero_end = html_content.find('</section>', html_content.find('<section class="hero">'))
            if hero_end > 0:
                html_content = (
                    html_content[:hero_end+10] +
                    status_html +
                    html_content[hero_end+10:]
                )
    except Exception:
        pass  # 상태 정보 추가 실패 시 무시
    
    # 뉴스 뷰어 스크립트 추가
    news_viewer_script = '''
        <script src="/all_news_viewer.js"></script>
    '''
    html_content = html_content.replace("</body>", news_viewer_script + "\n</body>")
    
    return html_content