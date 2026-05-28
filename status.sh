#!/usr/bin/env bash

echo "🔍 서버 상태 확인..."
echo ""

# API 서버 (포트 8000)
if lsof -i :8000 >/dev/null 2>&1; then
  echo "✅ API Server (8000): RUNNING"
else
  echo "❌ API Server (8000): STOPPED"
fi

# Vite 서버 (포트 5173)
if lsof -i :5173 >/dev/null 2>&1; then
  echo "✅ Vite Server (5173): RUNNING"
else
  echo "❌ Vite Server (5173): STOPPED"
fi

echo ""

# 헬스 체크
if command -v curl >/dev/null 2>&1; then
  if curl -s http://localhost:8000/api/healthz >/dev/null 2>&1; then
    echo "✅ API Health: OK"
  else
    echo "❌ API Health: FAIL"
  fi
fi

echo ""
echo "🔍 스크래퍼 상태 확인..."
echo ""

show_processes() {
  local label="$1"
  local pattern="$2"
  local matches
  matches="$(pgrep -fl "$pattern" 2>/dev/null || true)"
  if [[ -n "$matches" ]]; then
    echo "✅ ${label}: RUNNING"
    echo "$matches" | sed 's/^/   /'
  else
    echo "❌ ${label}: STOPPED"
  fi
}

show_processes "Full collect runner" "run_collect_once.sh"
show_processes "Watch loop" "src/watch/loop.py"
show_processes "Main scraper" "src/watch/scraper.py"
show_processes "Browser probe" "browser_probe.js"
show_processes "LinkedIn posts" "src/watch/linkedin_posts.py|linkedin_posts_probe.js"
show_processes "LinkedIn jobs spot" "src/watch/linkedin_jobs_spot.py|browser_probe_cdp.js"
show_processes "Telegram poller" "src/api/telegram_poller.py"

echo ""
if [[ -f "/Users/lewis/Desktop/agent/outputs/scrape_state.json" ]]; then
  echo "📄 scrape_state.json:"
  python3 - <<'PY' 2>/dev/null || true
import json
from pathlib import Path

path = Path("/Users/lewis/Desktop/agent/outputs/scrape_state.json")
data = json.loads(path.read_text(encoding="utf-8"))
for key in ("run_status", "started_at", "completed_at", "next_scrape_at", "new_jobs_this_run", "new_news_this_run"):
    if key in data:
        print(f"   {key}: {data[key]}")
PY
fi

echo ""
echo "최근 브라우저 진행 로그는 실행 중인 터미널에 직접 표시됩니다."
