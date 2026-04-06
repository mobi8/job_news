#!/usr/bin/env python3

"""
대시보드 핸들러 - 모든 API 엔드포인트 처리
"""

import http.server
import json
import os
import subprocess
import sqlite3
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from services.dashboard_utils import (
    load_json, send_json_response, 
    get_all_news_articles, render_dashboard_html
)

OUTPUT_DIR = Path("/Users/lewis/Desktop/agent/outputs")
FEEDBACK_PATH = OUTPUT_DIR / "reject_feedback.json"
WATCH_SETTINGS_PATH = OUTPUT_DIR / "watch_settings.json"
SCRAPE_STATE_PATH = OUTPUT_DIR / "scrape_state.json"
DASHBOARD_DATA_PATH = OUTPUT_DIR / "job_stats_data.json"
SCRAPER_PATH = str(Path(__file__).parent.parent / "core" / "scraper.py")

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUTPUT_DIR), **kwargs)
    
    def log_message(self, format, *args):
        """Override to use our logger instead of print."""
        from utils.logger import dashboard_logger
        dashboard_logger.debug(format % args)
    
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()
    
    def do_POST(self):
        """POST 요청 처리"""
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self.send_error(400, "Invalid JSON")
            return
        
        if self.path == "/reject-feedback":
            self.handle_reject_feedback(payload)
            return
        elif self.path == "/watch-settings":
            self.handle_watch_settings(payload)
            return
        elif self.path == "/run-scrape":
            self.handle_run_scrape(payload)
            return
        
        self.send_error(404, "Not found")
    
    def do_GET(self):
        """GET 요청 처리"""
        # API 엔드포인트
        if self.path == "/watch-settings":
            self.handle_get_watch_settings()
            return
        elif self.path == "/scrape-state":
            self.handle_get_scrape_state()
            return
        elif self.path == "/api/services-status":
            self.handle_get_services_status()
            return
        elif self.path == "/api/recent-news":
            self.handle_get_recent_news()
            return
        elif self.path == "/api/all-news":
            self.handle_get_all_news()
            return
        elif self.path == "/api/health":
            self.handle_get_health()
            return
        elif self.path == "/api-status":
            self.handle_get_api_status()
            return
        elif self.path == "/job_stats_dashboard.html":
            self.handle_get_dashboard()
            return
        elif self.path == "/all_news_viewer.js":
            self.handle_get_news_viewer_js()
            return
        
        # 기본 파일 서빙
        return super().do_GET()
    
    # POST 핸들러 메서드들
    def handle_reject_feedback(self, payload):
        FEEDBACK_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        from utils.logger import dashboard_logger
        dashboard_logger.info(f"Reject feedback saved: {len(payload)} items")
        send_json_response(self, {"ok": True})
    
    def handle_watch_settings(self, payload):
        current = load_json(WATCH_SETTINGS_PATH, {"scrape_interval_minutes": 1440})
        new_interval = max(1, int(payload.get("scrape_interval_minutes", current["scrape_interval_minutes"])))
        current["scrape_interval_minutes"] = new_interval
        WATCH_SETTINGS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        from utils.logger import dashboard_logger
        dashboard_logger.info(f"Watch settings updated: interval={new_interval} minutes")
        send_json_response(self, {"ok": True, "settings": current})
    
    def handle_run_scrape(self, payload):
        mode = str(payload.get("mode", "daily")).strip().lower() or "daily"
        if mode not in {"collect", "incremental", "daily"}:
            mode = "daily"
        from utils.logger import dashboard_logger
        dashboard_logger.info(f"Manual scrape triggered: mode={mode}")
        env = os.environ.copy()
        subprocess.Popen(
            ["python3", SCRAPER_PATH, mode],
            cwd="/Users/lewis/Desktop/agent",
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        send_json_response(self, {"ok": True, "started": True, "mode": mode})
    
    # GET 핸들러 메서드들
    def handle_get_watch_settings(self):
        send_json_response(self, load_json(WATCH_SETTINGS_PATH, {"scrape_interval_minutes": 1440}))
    
    def handle_get_scrape_state(self):
        send_json_response(self, load_json(SCRAPE_STATE_PATH, {}))
    
    def handle_get_services_status(self):
        try:
            from services_status import get_all_status
            send_json_response(self, get_all_status())
        except ImportError:
            send_json_response(self, {"services": [], "error": "services_status module not found"})
    
    def handle_get_recent_news(self):
        dashboard_data = load_json(DASHBOARD_DATA_PATH, {})
        send_json_response(self, {
            "topics": dashboard_data.get("topics", []),
            "count": len(dashboard_data.get("topics", [])),
            "player_mentions": dashboard_data.get("player_mentions", {}),
            "ai_insights": dashboard_data.get("ai_insights", {}),
        })
    
    def handle_get_all_news(self):
        """모든 뉴스 기사 조회 API"""
        try:
            result = get_all_news_articles(self.path, OUTPUT_DIR / "jobs.sqlite3")
            send_json_response(self, result)
        except Exception as e:
            from utils.logger import dashboard_logger
            dashboard_logger.error(f"Error fetching all news: {e}")
            send_json_response(self, {"articles": [], "total": 0, "error": str(e)})
    
    def handle_get_health(self):
        import time
        now = time.time()
        health = {
            "timestamp": now,
            "status": "healthy",
            "apis": {
                "recent-news": {"endpoint": "/api/recent-news", "status": "operational"},
                "all-news": {"endpoint": "/api/all-news", "status": "operational"},
                "watch-settings": {"endpoint": "/watch-settings", "status": "operational"},
                "scrape-state": {"endpoint": "/scrape-state", "status": "operational"},
            },
            "database": {
                "path": str(OUTPUT_DIR / "jobs.sqlite3"),
                "status": "operational" if (OUTPUT_DIR / "jobs.sqlite3").exists() else "offline"
            },
            "news_sources": [
                {"source": "rss_igaming_business", "label": "🎮 iGaming Business", "url": "https://igamingbusiness.com/feed/"},
                {"source": "rss_fintech_uae", "label": "💰 Fintech News UAE", "url": "https://fintechnews.ae/feed/"},
                {"source": "rss_intergame_news", "label": "🎲 InterGame News", "url": "https://www.intergameonline.com/rss/igaming/news"},
                {"source": "rss_intergame_crypto", "label": "₿ InterGame Crypto", "url": "https://www.intergameonline.com/rss/igaming/cryptocurrency"},
                {"source": "rss_intergame_all", "label": "🎰 InterGame All", "url": "https://www.intergameonline.com/rss/igaming/all"},
                {"source": "rss_intergame_abbrev", "label": "📰 InterGame Abbrev", "url": "https://www.intergameonline.com/rss/igaming/abbreviated"},
                {"source": "rss_finextra_headlines", "label": "📈 FinExtra Headlines", "url": "https://www.finextra.com/rss/headlines.aspx"},
                {"source": "rss_finextra_payments", "label": "💳 FinExtra Payments", "url": "https://www.finextra.com/rss/channel.aspx?channel=payments"},
                {"source": "rss_finextra_crypto", "label": "🔗 FinExtra Crypto", "url": "https://www.finextra.com/rss/channel.aspx?channel=crypto"}
            ]
        }
        send_json_response(self, health)
    
    def handle_get_api_status(self):
        import time
        import os
        
        def get_file_status(path):
            if not path.exists():
                return {"status": "offline", "exists": False, "last_modified": None}
            try:
                mtime = os.path.getmtime(path)
                return {"status": "online", "exists": True, "last_modified": mtime}
            except:
                return {"status": "error", "exists": True, "last_modified": None}
        
        state = {
            "timestamp": time.time(),
            "endpoints": {
                "scrape_state": get_file_status(SCRAPE_STATE_PATH),
                "watch_settings": get_file_status(WATCH_SETTINGS_PATH),
                "reject_feedback": get_file_status(FEEDBACK_PATH),
            }
        }
        send_json_response(self, state)
    
    def handle_get_dashboard(self):
        html_path = OUTPUT_DIR / "job_stats_dashboard.html"
        if not html_path.exists():
            self.send_error(404, "Dashboard HTML not found")
            return
        
        html_content = render_dashboard_html(html_path, OUTPUT_DIR)
        
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Content-Length", str(len(html_content.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))
    
    def handle_get_news_viewer_js(self):
        """뉴스 뷰어 JavaScript 파일 서빙"""
        js_content = """
// 간단한 뉴스 뷰어
document.addEventListener('DOMContentLoaded', function() {
    // 대시보드에 모든 뉴스 섹션 추가
    const newsSection = document.createElement('div');
    newsSection.innerHTML = `
        <div style="margin: 20px 0; padding: 20px; background: rgba(0,0,0,0.05); border-radius: 10px;">
            <h3 style="margin: 0 0 15px 0; color: #60a5fa;">📰 모든 뉴스 기사</h3>
            <div style="margin-bottom: 10px;">
                <a href="/api/all-news" target="_blank" 
                   style="color: #60a5fa; text-decoration: none; font-weight: 500;">
                    🔗 JSON 형식으로 모든 기사 보기
                </a>
            </div>
            <div id="news-preview" style="font-size: 13px; color: #9ca3af;">
                총 <span id="news-count">0</span>개 기사
            </div>
        </div>
    `;
    
    // 대시보드에 추가
    const hero = document.querySelector('.hero');
    if (hero) {
        hero.parentNode.insertBefore(newsSection, hero.nextSibling);
    }
    
    // 뉴스 개수 업데이트
    fetch('/api/all-news?limit=1')
        .then(res => res.json())
        .then(data => {
            document.getElementById('news-count').textContent = data.total || 0;
        })
        .catch(err => {
            console.error('뉴스 개수 로딩 실패:', err);
        });
});
        """;
        
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(js_content.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(js_content.encode("utf-8"))