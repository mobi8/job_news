#!/usr/bin/env python3

import http.server
import json
import socketserver
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.logger import dashboard_logger

OUTPUT_DIR = Path("/Users/lewis/Desktop/agent/outputs")
PORT = 8765

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

class MinimalDashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUTPUT_DIR), **kwargs)
    
    def log_message(self, format, *args):
        dashboard_logger.debug(format % args)
    
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()
    
    def do_GET(self):
        # 기본 파일 서빙
        if self.path == "/":
            self.path = "/job_stats_dashboard.html"
        
        return super().do_GET()

def main() -> int:
    with ReusableTCPServer(("127.0.0.1", PORT), MinimalDashboardHandler) as httpd:
        dashboard_logger.info(f"대시보드 실행 중: http://127.0.0.1:{PORT}/job_stats_dashboard.html")
        dashboard_logger.info(f"모든 뉴스 API: http://127.0.0.1:{PORT}/api/all-news")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            dashboard_logger.info("대시보드 서버 종료")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())