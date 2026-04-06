#!/usr/bin/env python3

from __future__ import annotations

import http.server
import json
import os
import subprocess
import socketserver
import sys
from pathlib import Path

# Add src/ to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.logger import dashboard_logger


OUTPUT_DIR = Path("/Users/lewis/Desktop/agent/outputs")
PORT = 8765
FEEDBACK_PATH = OUTPUT_DIR / "reject_feedback.json"
WATCH_SETTINGS_PATH = OUTPUT_DIR / "watch_settings.json"
SCRAPE_STATE_PATH = OUTPUT_DIR / "scrape_state.json"
DASHBOARD_DATA_PATH = OUTPUT_DIR / "job_stats_data.json"
# Updated path: scraper.py is now in src/core/
SCRAPER_PATH = str(Path(__file__).parent.parent / "core" / "scraper.py")


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUTPUT_DIR), **kwargs)

    def log_message(self, format, *args):
        """Override to use our logger instead of print."""
        dashboard_logger.debug(format % args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            dashboard_logger.warning(f"Invalid JSON received for {self.path}")
            self.send_error(400, "Invalid JSON")
            return

        if self.path == "/reject-feedback":
            FEEDBACK_PATH.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            dashboard_logger.info(f"Reject feedback saved: {len(payload)} items")
            self._send_json({"ok": True})
            return

        if self.path == "/watch-settings":
            current = self._load_json(WATCH_SETTINGS_PATH, self._default_settings())
            new_interval = max(1, int(payload.get("scrape_interval_minutes", current["scrape_interval_minutes"])))
            current["scrape_interval_minutes"] = new_interval
            WATCH_SETTINGS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
            dashboard_logger.info(f"Watch settings updated: interval={new_interval} minutes")
            self._send_json({"ok": True, "settings": current})
            return

        if self.path == "/run-scrape":
            mode = str(payload.get("mode", "daily")).strip().lower() or "daily"
            if mode not in {"collect", "incremental", "daily"}:
                mode = "daily"
            dashboard_logger.info(f"Manual scrape triggered: mode={mode}")
            env = os.environ.copy()
            subprocess.Popen(
                ["python3", SCRAPER_PATH, mode],
                cwd="/Users/lewis/Desktop/agent",
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._send_json({"ok": True, "started": True, "mode": mode})
            return

        dashboard_logger.warning(f"Unknown POST endpoint: {self.path}")
        self.send_error(404, "Not found")

    def do_GET(self):
        if self.path == "/watch-settings":
            self._send_json(self._load_json(WATCH_SETTINGS_PATH, self._default_settings()))
            return
        if self.path == "/scrape-state":
            self._send_json(self._load_json(SCRAPE_STATE_PATH, {}))
            return
        if self.path == "/api/services-status":
            from services_status import get_all_status
            self._send_json(get_all_status())
            return
        if self.path == "/api/recent-news":
            dashboard_data = self._load_json(DASHBOARD_DATA_PATH, {})
            topics = dashboard_data.get("topics", [])
            player_mentions = dashboard_data.get("player_mentions", {})
            ai_insights = dashboard_data.get("ai_insights", {})
            self._send_json({
                "topics": topics,
                "count": len(topics),
                "player_mentions": player_mentions,
                "ai_insights": ai_insights,
            })
            return
        if self.path == "/api/all-news":
            # 모든 뉴스 기사 조회 API
            try:
                db_path = OUTPUT_DIR / "jobs.sqlite3"
                if not db_path.exists():
                    self._send_json({"articles": [], "total": 0, "sources": {}})
                    return
                    
                import sqlite3
                import urllib.parse
                from datetime import datetime, timedelta
                
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                
                # 쿼리 파라미터 처리
                from urllib.parse import urlparse, parse_qs
                parsed_url = urlparse(self.path)
                query_params = parse_qs(parsed_url.query)
                source_filter = query_params.get('source', [None])[0]
                search_query = query_params.get('q', [None])[0]
                limit = int(query_params.get('limit', ['50'])[0])
                offset = int(query_params.get('offset', ['0'])[0])
                
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
                
                self._send_json({
                    "articles": articles,
                    "total": total_count,
                    "page_size": limit,
                    "offset": offset,
                    "source_stats": source_stats,
                    "sources": list(source_mapping.values())
                })
                return
                
            except Exception as e:
                dashboard_logger.error(f"Error fetching all news: {e}")
                self._send_json({"articles": [], "total": 0, "error": str(e)})
                return
        if self.path == "/api/health":
            import time
            now = time.time()
            health = {
                "timestamp": now,
                "status": "healthy",
                "apis": {
                    "recent-news": {
                        "endpoint": "/api/recent-news",
                        "status": "operational",
                        "description": "뉴스 아이템 조회",
                        "sample_response": {"news_items": [], "count": 0}
                    },
                    "watch-settings": {
                        "endpoint": "/watch-settings",
                        "status": "operational",
                        "description": "스크래핑 간격 설정 조회/수정",
                        "sample_response": {"scrape_interval_minutes": 60}
                    },
                    "scrape-state": {
                        "endpoint": "/scrape-state",
                        "status": "operational",
                        "description": "최종 스크래핑 상태 조회",
                        "sample_response": {}
                    },
                    "run-scrape": {
                        "endpoint": "/run-scrape (POST)",
                        "status": "operational",
                        "description": "스크래핑 즉시 실행 (daily/incremental/collect 모드)",
                        "sample_payload": {"mode": "daily"}
                    },
                    "reject-feedback": {
                        "endpoint": "/reject-feedback",
                        "status": "operational",
                        "description": "제외 피드백 조회/저장",
                        "sample_response": []
                    },
                    "api-status": {
                        "endpoint": "/api-status",
                        "status": "operational",
                        "description": "설정 파일 상태 확인",
                        "sample_response": {"timestamp": now, "endpoints": {}}
                    }
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
            self._send_json(health)
            return
        if self.path == "/job_stats_dashboard.html":
            html_path = OUTPUT_DIR / "job_stats_dashboard.html"
            if html_path.exists():
                html_content = html_path.read_text(encoding="utf-8")

                # 1) 배치 상태 + 서비스 상태를 hero 아래에 좌우 2열로 삽입 (접을 수 있도록)
                combined_status = self._render_batch_and_services_html()
                if combined_status and '<section class="hero">' in html_content:
                    hero_end = html_content.find('</section>', html_content.find('<section class="hero">'))
                    if hero_end > 0:
                        html_content = (
                            html_content[:hero_end+10] +
                            combined_status +
                            html_content[hero_end+10:]
                        )

                # 2) 동적 섹션 (토픽, 플레이어) JavaScript 주입
                news_injection = self._get_news_section_injection()
                html_content = html_content.replace("</body>", news_injection + "\n</body>")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Content-Length", str(len(html_content.encode("utf-8"))))
                self.end_headers()
                self.wfile.write(html_content.encode("utf-8"))
                return
            else:
                self.send_error(404, "Dashboard HTML not found")
                return
        if self.path == "/api-status":
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
            self._send_json(state)
            return
        
        if self.path == "/all-news.html":
            # 모든 뉴스 보기 페이지
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            
            html = '''
        return super().do_GET()

    def _default_settings(self):
        return {"scrape_interval_minutes": 1440}

    def _load_json(self, path: Path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _render_batch_and_services_html(self) -> str:
        """배치 상태와 서비스 상태를 좌우 2열로 배치 (토글 가능, 기본 닫힘)."""
        try:
            batch_html = self._render_batch_status_detailed_html()
            services_html, has_error = self._render_services_status_detailed_html()

            # 배치 상태 헤더 요약
            state_path = OUTPUT_DIR / "scrape_state.json"
            state = {}
            if state_path.exists():
                state = json.loads(state_path.read_text(encoding="utf-8"))

            mode = state.get("mode", "—")
            last_at = state.get("last_scraped_at", "")
            new_jobs = state.get("new_jobs_this_run", 0)

            if last_at:
                try:
                    from datetime import datetime
                    last_dt = datetime.fromisoformat(last_at.replace("Z", "+00:00"))
                    now = datetime.utcnow()
                    if last_dt.tzinfo:
                        last_dt = last_dt.replace(tzinfo=None)
                    elapsed = now - last_dt
                    hours = int(elapsed.total_seconds() // 3600)
                    minutes = int((elapsed.total_seconds() % 3600) // 60)
                    if hours > 0:
                        elapsed_str = f"{hours}h {minutes}m"
                    else:
                        elapsed_str = f"{minutes}m"
                    batch_time = last_dt.strftime("%H:%M")
                except Exception:
                    elapsed_str = "—"
                    batch_time = "—"
            else:
                elapsed_str = "—"
                batch_time = "—"

            error_badge = " ⚠️" if has_error else ""

            h = [
                '<div style="margin-top:8px;display:grid;grid-template-columns:minmax(400px,1fr) minmax(400px,1fr);gap:8px;width:100%;">',
                '<script>function toggleBatch(){const b=document.getElementById("batch-toggle-body");const i=document.getElementById("batch-toggle-icon");if(b.style.display==="none"){b.style.display="block";i.style.transform="rotate(180deg)"}else{b.style.display="none";i.style.transform="rotate(0deg)"}}function toggleServices(){const b=document.getElementById("services-toggle-body");const i=document.getElementById("services-toggle-icon");if(b.style.display==="none"){b.style.display="block";i.style.transform="rotate(180deg)"}else{b.style.display="none";i.style.transform="rotate(0deg)"}}</script>',
                # 좌측: 배치 상태
                '<div style="background:linear-gradient(135deg,rgba(255,255,255,0.05) 0%,rgba(255,255,255,0.04) 100%);border:1px solid rgba(255,255,255,0.1);border-radius:10px;backdrop-filter:blur(12px);overflow:hidden;display:flex;flex-direction:column;box-shadow:0 2px 8px rgba(0,0,0,0.2),inset 0 1px 0 rgba(255,255,255,0.05);">',
                '<div style="padding:8px 10px;background:rgba(255,255,255,0.03);border-bottom:1px solid rgba(255,255,255,0.1);display:flex;justify-content:space-between;align-items:center;cursor:pointer;flex-shrink:0;" onclick="toggleBatch()">',
                f'<div style="flex:1;font-size:11px;color:var(--text-primary);"><strong>배치 상태</strong><span style="margin-left:10px;color:var(--text-muted);font-size:10px;">모드: <strong>{mode}</strong> | 마지막: <strong>{elapsed_str}</strong> ({batch_time}) | 신규: <strong style="color:#60a5fa;">{new_jobs}건</strong></span></div>',
                '<span id="batch-toggle-icon" style="display:inline-block;width:10px;font-size:8px;color:var(--text-muted);transition:transform 0.2s;flex-shrink:0;margin-left:6px;">▶</span>',
                '</div>',
                f'<div id="batch-toggle-body" style="padding:8px;overflow-y:auto;flex:1;display:none;color:var(--text-secondary);font-size:0.8rem;">{batch_html}</div>',
                '</div>',
                # 우측: 서비스 상태
                '<div style="background:linear-gradient(135deg,rgba(255,255,255,0.05) 0%,rgba(255,255,255,0.04) 100%);border:1px solid rgba(255,255,255,0.1);border-radius:10px;backdrop-filter:blur(12px);overflow:hidden;display:flex;flex-direction:column;box-shadow:0 2px 8px rgba(0,0,0,0.2),inset 0 1px 0 rgba(255,255,255,0.05);">',
                '<div style="padding:8px 10px;background:rgba(255,255,255,0.03);border-bottom:1px solid rgba(255,255,255,0.1);display:flex;justify-content:space-between;align-items:center;cursor:pointer;flex-shrink:0;" onclick="toggleServices()">',
                f'<div style="flex:1;font-size:11px;color:var(--text-primary);"><strong>서비스 상태</strong><span style="margin-left:10px;color:var(--text-muted);font-size:10px;">{error_badge}</span></div>',
                '<span id="services-toggle-icon" style="display:inline-block;width:10px;font-size:8px;color:var(--text-muted);transition:transform 0.2s;flex-shrink:0;margin-left:6px;">▶</span>',
                '</div>',
                f'<div id="services-toggle-body" style="padding:8px;overflow-y:auto;flex:1;display:none;color:var(--text-secondary);font-size:0.8rem;">{services_html}</div>',
                '</div>',
                '</div>',
            ]
            return "\n".join(h)
        except Exception as e:
            return f"<!-- 배치 상태 오류: {e} -->"

    def _render_batch_status_detailed_html(self) -> str:
        """배치 작업 상태를 리스트 형식으로 렌더링."""
        try:
            from datetime import datetime
            import html as _html

            state_path = OUTPUT_DIR / "scrape_state.json"
            dashboard_path = OUTPUT_DIR / "job_stats_data.json"
            if not state_path.exists():
                return ""

            state = json.loads(state_path.read_text(encoding="utf-8"))
            dashboard_data = json.loads(dashboard_path.read_text(encoding="utf-8")) if dashboard_path.exists() else {}

            sources = state.get("sources", {})
            news_items = dashboard_data.get("news_items", [])
            topics = dashboard_data.get("topics", [])

            h = [
                '<div style="font-size:10px;color:var(--text-secondary);">',
                '<div style="margin-bottom:6px;color:var(--text-primary);"><strong style="font-size:11px;">채용 공고 소스</strong></div>',
            ]

            # 모든 채용 소스 (스크래핑 방식 표시)
            scraping_methods = {
                "jobvite_pragmaticplay": "HTML",
                "smartrecruitment": "HTML",
                "igamingrecruitment": "HTML",
                "jobrapido_uae": "HTML",
                "jobleads": "HTML",
                "telegram_job_crypto_uae": "RSS",
                "telegram_cryptojobslist": "RSS",
                "indeed_uae": "Playwright",
                "linkedin_public": "Playwright",
            }

            job_sources = [
                ("jobvite_pragmaticplay", "Jobvite"),
                ("smartrecruitment", "SmartRecruitment"),
                ("igamingrecruitment", "iGaming Recruitment"),
                ("jobrapido_uae", "Jobrapido"),
                ("jobleads", "JobLeads"),
                ("telegram_job_crypto_uae", "Telegram (Jobs Crypto)"),
                ("telegram_cryptojobslist", "Telegram (CryptoJobsList)"),
                ("indeed_uae", "Indeed UAE"),
                ("linkedin_public", "LinkedIn"),
            ]

            for src_key, src_name in job_sources:
                src_data = sources.get(src_key, {})
                total_count = src_data.get("count", 0) if src_data else 0
                added_count = src_data.get("added_this_batch", 0) if src_data else 0
                src_at = src_data.get("last_scraped_at", "") if src_data else ""
                method = scraping_methods.get(src_key, "—")

                if src_at:
                    try:
                        src_dt = datetime.fromisoformat(src_at.replace("Z", "+00:00"))
                        now = datetime.utcnow()
                        if src_dt.tzinfo:
                            src_dt = src_dt.replace(tzinfo=None)
                        src_elapsed = now - src_dt
                        src_minutes = int((src_elapsed.total_seconds() % 3600) // 60)
                        src_time = f"{src_minutes}m"
                    except Exception:
                        src_time = "—"
                else:
                    src_time = "—"

                status_color = "#10b981" if total_count > 0 else "#9ca3af"

                h.append(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid rgba(0,0,0,0.04);font-size:10px;">'
                    f'<div style="flex:1;font-weight:500;color:{status_color};">{_html.escape(src_name)} <span style="color:var(--muted);font-weight:400;font-size:9px;">({method})</span></div>'
                    f'<div style="display:flex;gap:14px;text-align:right;color:var(--muted);min-width:120px;font-size:10px;">'
                    f'<span><strong style="color:{status_color};">{total_count}</strong> <span style="font-size:9px;">(+{added_count})</span></span>'
                    f'<span style="min-width:28px;">{src_time}</span>'
                    f'</div>'
                    f'</div>'
                )

            # 뉴스 소스별 개수 계산 (scrape_state.json에서)
            h.append('<div style="margin-top:12px;margin-bottom:10px;"><strong>뉴스 소스</strong></div>')

            # scrape_state.json에서 뉴스 소스 데이터 읽기
            news_sources_data = {}
            try:
                state = json.loads((OUTPUT_DIR / "scrape_state.json").read_text(encoding="utf-8"))
                news_sources_data = state.get("news_sources", {})
            except Exception:
                pass

            news_sources_info = [
                ("rss_igaming_business", "iGaming Business", "RSS"),
                ("rss_fintech_uae", "Fintech News UAE", "RSS"),
                ("player_feed", "플레이어 피드", "RSS"),
            ]

            for src_key, src_name, method in news_sources_info:
                src_info = news_sources_data.get(src_key, {})
                count = src_info.get("count", 0)
                added_count = src_info.get("added_this_batch", 0)
                src_at = src_info.get("last_scraped_at", "")

                if src_at:
                    try:
                        from datetime import datetime
                        src_dt = datetime.fromisoformat(src_at.replace("Z", "+00:00"))
                        now = datetime.utcnow()
                        if src_dt.tzinfo:
                            src_dt = src_dt.replace(tzinfo=None)
                        src_elapsed = now - src_dt
                        src_minutes = int((src_elapsed.total_seconds() % 3600) // 60)
                        src_time = f"{src_minutes}m"
                    except Exception:
                        src_time = "—"
                else:
                    src_time = "—"

                status_color = "#10b981" if count > 0 else "#9ca3af"
                unit = "개" if src_key == "player_feed" else "건"

                h.append(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid rgba(0,0,0,0.04);font-size:10px;">'
                    f'<div style="flex:1;font-weight:500;color:{status_color};">{_html.escape(src_name)} <span style="color:var(--muted);font-weight:400;font-size:9px;">({method})</span></div>'
                    f'<div style="display:flex;gap:14px;text-align:right;color:var(--muted);min-width:120px;font-size:10px;">'
                    f'<span><strong style="color:{status_color};">{count}{unit}</strong> <span style="font-size:9px;">(+{added_count}{unit})</span></span>'
                    f'<span style="min-width:28px;">{src_time}</span>'
                    f'</div>'
                    f'</div>'
                )

            h.append('</div>')
            return "\n".join(h)
        except Exception as e:
            return f"<!-- 배치 상태 오류: {e} -->"

    def _render_batch_status_html(self) -> str:
        """배치 작업 상태와 모든 소스 갱신 상태를 설정 섹션용으로 렌더링."""
        try:
            from datetime import datetime
            import html as _html

            state_path = OUTPUT_DIR / "scrape_state.json"
            if not state_path.exists():
                return ""

            state = json.loads(state_path.read_text(encoding="utf-8"))
            last_at = state.get("last_scraped_at", "")
            mode = state.get("mode", "unknown")
            new_jobs = state.get("new_jobs_this_run", 0)
            sources = state.get("sources", {})

            if last_at:
                try:
                    last_dt = datetime.fromisoformat(last_at.replace("Z", "+00:00"))
                    now = datetime.utcnow()
                    if last_dt.tzinfo:
                        last_dt = last_dt.replace(tzinfo=None)
                    elapsed = now - last_dt
                    hours = int(elapsed.total_seconds() // 3600)
                    minutes = int((elapsed.total_seconds() % 3600) // 60)
                    if hours > 0:
                        elapsed_str = f"{hours}h {minutes}m"
                    else:
                        elapsed_str = f"{minutes}m"
                except Exception:
                    elapsed_str = "—"
            else:
                elapsed_str = "—"

            h = [
                '<div style="display:grid;grid-template-columns:100px 1fr;gap:12px;margin-bottom:10px;align-items:start;">',
                '<div style="color:#666;font-weight:500;">배치 상태</div>',
                '<div style="color:#333;line-height:1.4;">',
                f'<strong>{_html.escape(mode)}</strong> 모드 · 전 {elapsed_str} · 신규 {new_jobs}건',
                '</div>',
                '</div>',
                '<div style="display:grid;grid-template-columns:100px 1fr;gap:12px;margin-bottom:10px;align-items:start;">',
                '<div style="color:#666;font-weight:500;">채용 소스</div>',
                '<div style="color:#333;line-height:1.4;font-size:11px;">',
            ]

            # 모든 채용 소스 (순서 중요, Telegram 제외)
            job_sources = [
                ("jobvite_pragmaticplay", "Jobvite"),
                ("smartrecruitment", "SmartRecruitment"),
                ("igamingrecruitment", "iGaming Recruitment"),
                ("jobrapido_uae", "Jobrapido"),
                ("jobleads", "JobLeads"),
                ("indeed_uae", "Indeed UAE"),
                ("linkedin_public", "LinkedIn"),
            ]

            job_lines = []
            for src_key, src_name in job_sources:
                src_data = sources.get(src_key, {})
                src_count = src_data.get("count", 0) if src_data else 0
                src_at = src_data.get("last_scraped_at", "") if src_data else ""

                if src_at:
                    try:
                        src_dt = datetime.fromisoformat(src_at.replace("Z", "+00:00"))
                        now = datetime.utcnow()
                        if src_dt.tzinfo:
                            src_dt = src_dt.replace(tzinfo=None)
                        src_elapsed = now - src_dt
                        src_hours = int(src_elapsed.total_seconds() // 3600)
                        src_minutes = int((src_elapsed.total_seconds() % 3600) // 60)
                        if src_hours > 0:
                            src_time = f"{src_hours}h"
                        else:
                            src_time = f"{src_minutes}m"
                    except Exception:
                        src_time = "—"
                else:
                    src_time = "—"

                job_lines.append(f'{_html.escape(src_name)}: {src_count}건 (전 {src_time})')

            h.append(' · '.join(job_lines))
            h.append('</div>')
            h.append('</div>')

            # 뉴스 소스
            h.append('<div style="display:grid;grid-template-columns:100px 1fr;gap:12px;align-items:start;">')
            h.append('<div style="color:#666;font-weight:500;">뉴스 소스</div>')
            h.append('<div style="color:#333;line-height:1.4;font-size:11px;">')
            h.append('iGaming Business · Fintech News UAE · 플레이어 피드')
            h.append('</div>')
            h.append('</div>')

            return "\n".join(h)
        except Exception as e:
            return f"<!-- 배치 상태 오류: {e} -->"

    def _render_services_status_detailed_html(self) -> tuple[str, bool]:
        """서비스 상태를 리스트 형식으로 렌더링. (HTML, has_error) 튜플 반환."""
        try:
            from services_status import get_all_status
            import html as _html

            status = get_all_status()
            services = status.get("services", [])

            h = [
                '<div style="font-size:11px;">',
            ]

            has_error = False

            for svc in services:
                is_enabled = svc["enabled"]
                status_color = "#10b981" if is_enabled else "#ef4444"
                check_icon = "✓" if is_enabled else "✗"
                details = svc.get("details", "")
                name = svc["name"].split(" (")[0]

                if not is_enabled:
                    has_error = True

                h.append(
                    f'<div style="display:grid;grid-template-columns:140px 25px 1fr;gap:8px;padding:5px 0;align-items:start;border-bottom:1px solid rgba(0,0,0,0.04);font-size:10px;">'
                    f'<div style="color:var(--ink);font-weight:500;">{_html.escape(name)}</div>'
                    f'<div style="text-align:center;color:{status_color};font-weight:700;">{check_icon}</div>'
                    f'<div style="color:var(--muted);font-size:9px;">{_html.escape(details)}</div>'
                    f'</div>'
                )

            h.append('</div>')
            return "\n".join(h), has_error
        except Exception:
            return "", False

    def _render_services_status_html(self) -> str:
        """서비스 상태를 설정 섹션용으로 렌더링."""
        try:
            from services_status import get_all_status
            import html as _html

            status = get_all_status()
            services = status.get("services", [])

            h = [
                '<div style="display:grid;grid-template-columns:100px 1fr;gap:12px;align-items:start;">',
                '<div style="color:#666;font-weight:500;">서비스</div>',
                '<div style="color:#333;line-height:1.4;font-size:11px;">',
            ]

            service_lines = []
            for svc in services:
                check = "O" if svc["enabled"] else "X"
                name = svc["name"].split(" (")[0]
                service_lines.append(f'{check} {_html.escape(name)}')

            h.append(' · '.join(service_lines))
            h.append('</div>')
            h.append('</div>')
            return "\n".join(h)
        except Exception:
            return ""

    def _send_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _get_news_section_injection(self):
        """Return JavaScript to inject topics and player sections."""
        # 간단한 모든 뉴스 뷰어 스크립트 로드
        return '''<script src="/all_news_viewer.js"></script>
// 모든 뉴스 탭 관리
let currentPage = 1;
const pageSize = 50;
let currentSource = 'all';
let currentSearch = '';

async function loadAllNews(page = 1, source = 'all', search = '') {
  try {
    const loader = document.getElementById('news-loader');
    const container = document.getElementById('all-news-container');
    const stats = document.getElementById('news-stats');
    
    loader.style.display = 'block';
    container.innerHTML = '';
    
    let url = `/api/all-news?limit=${pageSize}&offset=${(page-1)*pageSize}`;
    if (source !== 'all') url += `&source=${encodeURIComponent(source)}`;
    if (search) url += `&q=${encodeURIComponent(search)}`;
    
    const res = await fetch(url);
    const data = await res.json();
    
    // 통계 표시
    stats.innerHTML = `<strong>${data.total}개 기사</strong> (${Object.entries(data.source_stats).map(([k,v]) => \`\${k}: \${v}\`).join(', ')})`;
    
    // 기사 목록 표시
    if (data.articles.length === 0) {
      container.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">검색 결과가 없습니다.</div>';
      return;
    }
    
    let newsHtml = '';
    data.articles.forEach((article, idx) => {
      const articleNum = (page-1) * pageSize + idx + 1;
      newsHtml += `
        <div style="margin-bottom: 16px; padding: 12px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
            <span style="font-size: 12px; color: #60a5fa; font-weight: 500;">${article.source_label}</span>
            <span style="font-size: 11px; color: #9ca3af;">${article.date}</span>
          </div>
          <a href="${article.url}" target="_blank" style="color: #fff; text-decoration: none; font-weight: 500; font-size: 14px; line-height: 1.4; display: block;">
            ${article.title}
          </a>
          ${article.summary ? `<div style="margin-top: 6px; font-size: 12px; color: #9ca3af; line-height: 1.4;">${article.summary.substring(0, 120)}...</div>` : ''}
        </div>
      `;
    });
    
    container.innerHTML = newsHtml;
    
    // 페이지네이션 업데이트
    updatePagination(data.total, page);
    
  } catch (err) {
    console.error('뉴스 로딩 실패:', err);
    document.getElementById('all-news-container').innerHTML = 
      '<div style="text-align: center; padding: 40px; color: #ef4444;">뉴스를 불러오는 중 오류가 발생했습니다.</div>';
  } finally {
    document.getElementById('news-loader').style.display = 'none';
  }
}

function updatePagination(total, currentPage) {
  const totalPages = Math.ceil(total / pageSize);
  const pagination = document.getElementById('news-pagination');
  
  let paginationHtml = '';
  
  if (totalPages > 1) {
    paginationHtml += '<div style="display: flex; gap: 6px; align-items: center; justify-content: center; margin-top: 20px;">';
    
    if (currentPage > 1) {
      paginationHtml += `<button onclick="loadAllNews(${currentPage-1}, currentSource, currentSearch)" style="padding: 6px 12px; background: rgba(96, 165, 250, 0.2); border: none; border-radius: 4px; color: #60a5fa; cursor: pointer;">이전</button>`;
    }
    
    for (let i = 1; i <= Math.min(totalPages, 5); i++) {
      if (i === currentPage) {
        paginationHtml += `<button style="padding: 6px 12px; background: #60a5fa; border: none; border-radius: 4px; color: white; cursor: pointer; font-weight: bold;">${i}</button>`;
      } else {
        paginationHtml += `<button onclick="loadAllNews(${i}, currentSource, currentSearch)" style="padding: 6px 12px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; color: #fff; cursor: pointer;">${i}</button>`;
      }
    }
    
    if (currentPage < totalPages) {
      paginationHtml += `<button onclick="loadAllNews(${currentPage+1}, currentSource, currentSearch)" style="padding: 6px 12px; background: rgba(96, 165, 250, 0.2); border: none; border-radius: 4px; color: #60a5fa; cursor: pointer;">다음</button>`;
    }
    
    paginationHtml += '</div>';
  }
  
  pagination.innerHTML = paginationHtml || '';
}

function searchNews() {
  const searchInput = document.getElementById('news-search');
  currentSearch = searchInput.value;
  currentPage = 1;
  loadAllNews(1, currentSource, currentSearch);
}

function filterBySource(source) {
  currentSource = source;
  currentPage = 1;
  loadAllNews(1, source, currentSearch);
}

// 기존 뉴스 섹션 코드와 통합
(async function() {
  try {
    // 뉴스 섹션 (토픽, 플레이어, 모든 뉴스)
    const res = await fetch('/api/recent-news');
    const data = await res.json();
    const topics = data.topics || [];
    const players = data.player_mentions || {};

    let html = '';

    // 1. Topics Section
    if (topics.length > 0) {
      html += '<section style="margin-top:20px;padding:14px 0;"><div class="wrap">';
      html += '<h2 style="margin:0 0 4px;font-size:1.5rem;font-weight:600;color:var(--text-primary);">📰 업계 토픽 동향</h2>';
      html += '<p class="meta" style="color:var(--text-muted);">' + topics.length + '개 주제 · 최근 7일 뉴스 기반</p>';
      html += '<div style="display:grid;gap:8px;margin-top:10px;">';

      topics.forEach((topic, idx) => {
        const topicId = 'topic-' + idx;
        const isExpanded = idx === 0;
        const display = isExpanded ? 'block' : 'none';

        html += '<div style="background:linear-gradient(135deg,rgba(255,255,255,0.05) 0%,rgba(255,255,255,0.04) 100%);border:1px solid rgba(255,255,255,0.1);border-radius:10px;overflow:hidden;backdrop-filter:blur(12px);box-shadow:0 2px 8px rgba(0,0,0,0.2),inset 0 1px 0 rgba(255,255,255,0.05);">';
        html += '<div style="padding:10px 12px;background:rgba(255,255,255,0.03);cursor:pointer;display:flex;justify-content:space-between;align-items:center;" onclick="document.getElementById(\'' + topicId + '\').style.display = (document.getElementById(\'' + topicId + '\').style.display === \'none\' ? \'block\' : \'none\')">';
        html += '<div style="flex:1;">';
        html += '<strong style="color:var(--text-primary);font-size:12px;">' + topic.label_ko + '</strong>';
        html += '<span style="font-size:11px;color:var(--text-muted);margin-left:8px;">' + topic.article_count + '건 · ' + topic.latest_date.substring(0, 10) + '</span>';
        html += '</div>';
        html += '<span style="color:var(--text-muted);font-size:10px;transition:transform 0.2s;">▼</span>';
        html += '</div>';

        html += '<div id="' + topicId + '" style="display:' + display + ';padding:10px;border-top:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.02);">';
        topic.articles.forEach((article, aIdx) => {
          const isLast = aIdx === topic.articles.length - 1;
          const borderBottom = isLast ? '' : 'border-bottom:1px solid rgba(255,255,255,0.05);padding-bottom:6px;margin-bottom:6px;';
          const pubDate = new Date(article.published_at).toLocaleDateString('en-US');
          // 소스 라벨 매핑
          const sourceMap = {
            'rss_igaming_business': '🎮 iGaming Business',
            'rss_fintech_uae': '💰 Fintech UAE',
            'rss_intergame_news': '🎲 InterGame News',
            'rss_intergame_crypto': '₿ InterGame Crypto',
            'rss_intergame_all': '🎰 InterGame All',
            'rss_intergame_abbrev': '📰 InterGame Abbrev',
            'rss_finextra_headlines': '📈 FinExtra',
            'rss_finextra_payments': '💳 FinExtra Payments',
            'rss_finextra_crypto': '🔗 FinExtra Crypto'
          };
          const source = sourceMap[article.source] || article.source;

          html += '<div style="' + borderBottom + '">';
          html += '<a href="' + escapeHtml(article.url, true) + '" target="_blank" style="color:var(--accent);text-decoration:none;font-size:12px;font-weight:500;line-height:1.35;transition:color 0.2s ease;" onmouseover="this.style.color=\'#90caf9\'" onmouseout="this.style.color=\'var(--accent)\'">' + escapeHtml(article.title.substring(0, 70)) + '</a>';
          if (article.summary) {
            html += '<div style="margin-top:2px;font-size:11px;color:var(--text-muted);line-height:1.4;">' + escapeHtml(article.summary.substring(0, 80)) + '...</div>';
          }
          html += '<div style="margin-top:3px;font-size:10px;color:var(--text-muted);">' + source + ' · ' + pubDate + '</div>';
          html += '</div>';
        });
        html += '</div>';
        html += '</div>';
      });

      html += '</div></div></section>';
    }

    // 3. Player Tracking Section
    if (players && Object.keys(players).length > 0) {
      html += '<section style="margin-top:20px;padding:14px 0;"><div class="wrap">';
      html += '<h2 style="margin:0 0 4px;font-size:1.5rem;font-weight:600;color:var(--text-primary);">👥 플레이어 활동</h2>';
      html += '<p class="meta" style="color:var(--text-muted);">' + Object.keys(players).length + '개 플레이어 · 최근 7일 멘션</p>';

      const playerEntries = Object.entries(players).sort((a, b) => (b[1].count||0) - (a[1].count||0));

      html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:6px;margin-top:10px;">';
      playerEntries.slice(0, 12).forEach(([name, data]) => {
        const count = data.count || 0;
        const trend = count >= 3 ? '🔥' : '→';
        html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:linear-gradient(135deg,rgba(255,255,255,0.05) 0%,rgba(255,255,255,0.04) 100%);border:1px solid rgba(255,255,255,0.1);border-radius:8px;backdrop-filter:blur(10px);">';
        html += '<span style="flex:1;font-size:11px;color:var(--text-secondary);">' + trend + ' ' + escapeHtml(name) + '</span>';
        html += '<span style="font-size:11px;font-weight:bold;color:var(--accent);">' + count + '</span>';
        html += '</div>';
      });
      html += '</div></div></section>';
    }

    // Insert topics & player sections after hero
    if (html) {
      const heroSection = document.querySelector('.hero');
      if (heroSection) {
        const div = document.createElement('div');
        div.innerHTML = html;
        const ref = heroSection.nextSibling;
        while (div.firstElementChild) {
          heroSection.parentNode.insertBefore(div.firstElementChild, ref);
        }
      }
    }
  } catch (err) {
    console.log('News sections failed to load:', err);
  }
})();

function escapeHtml(text, isUrl) {
  if (isUrl) {
    return text.replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return text.replace(/[&<>"']/g, m => map[m]);
}
</script>'''


def main() -> int:
    with ReusableTCPServer(("127.0.0.1", PORT), DashboardHandler) as httpd:
        dashboard_logger.info(f"Dashboard available at http://127.0.0.1:{PORT}/job_stats_dashboard.html")
        httpd.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
