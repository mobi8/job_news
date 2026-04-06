#!/usr/bin/env python3

import http.server
import json
import socketserver
import sys
from pathlib import Path
import sqlite3
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent.parent))

OUTPUT_DIR = Path("/Users/lewis/Desktop/agent/outputs")
PORT = 8765

class SimpleDashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUTPUT_DIR), **kwargs)
    
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        super().end_headers()
    
    def do_GET(self):
        if self.path == "/api/all-news":
            self.handle_all_news()
            return
        elif self.path == "/":
            self.send_response(302)
            self.send_header("Location", "/job_stats_dashboard.html")
            self.end_headers()
            return
        
        return super().do_GET()
    
    def handle_all_news(self):
        try:
            db_path = OUTPUT_DIR / "jobs.sqlite3"
            if not db_path.exists():
                self.send_json({"articles": [], "total": 0})
                return
            
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            limit = int(query_params.get('limit', ['20'])[0])
            offset = int(query_params.get('offset', ['0'])[0])
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            cursor.execute("SELECT source, title, url, published_at, summary FROM news ORDER BY published_at DESC LIMIT ? OFFSET ?", 
                          [limit, offset])
            
            articles = []
            for source, title, url, published_at, summary in cursor.fetchall():
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
                
                articles.append({
                    "source": source_mapping.get(source, source),
                    "title": title,
                    "url": url,
                    "published_at": published_at,
                    "summary": summary,
                    "date": published_at[:10] if published_at else ""
                })
            
            cursor.execute("SELECT COUNT(*) FROM news")
            total = cursor.fetchone()[0]
            
            conn.close()
            
            self.send_json({
                "articles": articles,
                "total": total,
                "page_size": limit,
                "offset": offset
            })
            
        except Exception as e:
            self.send_json({"articles": [], "total": 0, "error": str(e)})
    
    def send_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def main():
    with socketserver.TCPServer(("127.0.0.1", PORT), SimpleDashboardHandler) as httpd:
        print(f"✅ 간단한 대시보드 서버 실행 중: http://127.0.0.1:{PORT}")
        print(f"📰 모든 뉴스 API: http://127.0.0.1:{PORT}/api/all-news")
        print(f"📊 대시보드: http://127.0.0.1:{PORT}/job_stats_dashboard.html")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n서버 종료")

if __name__ == "__main__":
    main()
