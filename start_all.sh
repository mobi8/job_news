#!/bin/bash

# 모든 서비스를 백그라운드에서 실행

set -e  # 에러 발생 시 중단

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 모든 서비스 시작..."
echo "================================================"

# 디렉토리 생성
mkdir -p .pids logs

# 기존 PID 파일 정리
if [ -f .pids/dashboard.pid ]; then
    echo "🧹 기존 대시보드 프로세스 정리..."
    kill -9 $(cat .pids/dashboard.pid) 2>/dev/null || true
    rm -f .pids/dashboard.pid
fi

if [ -f .pids/watch.pid ]; then
    echo "🧹 기존 워치 프로세스 정리..."
    kill -9 $(cat .pids/watch.pid) 2>/dev/null || true
    rm -f .pids/watch.pid
fi

if [ -f .pids/telegram.pid ]; then
    echo "🧹 기존 텔레그램 프로세스 정리..."
    kill -9 $(cat .pids/telegram.pid) 2>/dev/null || true
    rm -f .pids/telegram.pid
fi

# 가상환경 활성화
if [ -d "venv" ]; then
    echo "🐍 가상환경 활성화..."
    source venv/bin/activate
else
    echo "⚠️  가상환경이 없습니다. 생성 중..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
fi

# 환경 변수 로드 (있으면)
if [ -f ".env" ]; then
    echo "🔧 환경 변수 로드..."
    export $(grep -v '^#' .env | xargs)
fi

echo ""

# 1. 대시보드 서버 (포트 8765)
echo "📊 1. 대시보드 서버 시작 (http://127.0.0.1:8765)..."
python3 src/services/serve_dashboard.py > logs/dashboard.log 2>&1 &
DASHBOARD_PID=$!
sleep 2
if ps -p $DASHBOARD_PID > /dev/null; then
    echo "   ✅ 성공! PID: $DASHBOARD_PID"
    echo "$DASHBOARD_PID" > .pids/dashboard.pid
else
    echo "   ❌ 실패! 로그 확인: logs/dashboard.log"
fi

# 2. 주기적 폴링 (watch_settings.json 기준으로 실행)
echo ""
echo "👁️  2. 주기적 수집 서비스 시작..."
python3 src/watch/loop.py > logs/watch_loop.log 2>&1 &
WATCH_PID=$!
sleep 2
if ps -p $WATCH_PID > /dev/null; then
    echo "   ✅ 성공! PID: $WATCH_PID"
    echo "$WATCH_PID" > .pids/watch.pid
else
    echo "   ❌ 실패! 로그 확인: logs/watch_loop.log"
fi

# 3. 텔레그램 알림 서비스 (RSS 피드 포함)
echo ""
echo "📨 3. 텔레그램 알림 서비스 시작..."
python3 src/watch/telegram_loop.py > logs/telegram.log 2>&1 &
TELEGRAM_PID=$!
sleep 2
if ps -p $TELEGRAM_PID > /dev/null; then
    echo "   ✅ 성공! PID: $TELEGRAM_PID"
    echo "$TELEGRAM_PID" > .pids/telegram.pid
else
    echo "   ❌ 실패! 로그 확인: logs/telegram.log"
    echo "   ℹ️  텔레그램 루프 파일이 없을 수 있습니다"
fi

echo ""
echo "================================================"
echo "✅ 모든 서비스 시작 완료!"
echo ""

# 현재 실행 상태 확인
echo "📋 실행 중인 프로세스:"
echo "------------------------------------------------"
ps aux | grep -E "serve_dashboard|loop\.py|telegram" | grep -v grep || echo "   (실행 중인 프로세스 없음)"
echo ""

# 서비스 상태 API 확인
echo "🌐 서비스 상태 확인:"
echo "------------------------------------------------"
sleep 3
if curl -s http://127.0.0.1:8765/api/health > /dev/null 2>&1; then
    echo "   ✅ 대시보드 API: http://127.0.0.1:8765/api/health"
    echo "   ✅ 대시보드 UI: http://127.0.0.1:8765/job_stats_dashboard.html"
else
    echo "   ❌ 대시보드 API 응답 없음"
fi

# RSS 피드 상태 확인
echo ""
echo "📰 RSS 피드 상태:"
echo "------------------------------------------------"
if [ -f "outputs/jobs.sqlite3" ]; then
    python3 -c "
import sqlite3
from pathlib import Path
db_path = Path('outputs/jobs.sqlite3')
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM news')
    total = cursor.fetchone()[0]
    cursor.execute('''SELECT COUNT(*) FROM news WHERE datetime(published_at) > datetime('now', '-24 hours')''')
    recent = cursor.fetchone()[0]
    print(f'   총 {total}개 기사, 최근 24시간: {recent}개')
    conn.close()
else:
    print('   데이터베이스 없음')
" 2>/dev/null || echo "   확인 불가"
fi

echo ""
echo "📁 로그 파일:"
echo "   - logs/dashboard.log"
echo "   - logs/watch_loop.log"
echo "   - logs/telegram.log"
echo "   - logs/scraper.log"
echo "   - logs/notifications.log"
echo ""
echo "❌ 모든 서비스 중지: ./stop_all.sh"
echo "👀 로그 확인: tail -f logs/*.log"
echo "🔄 서비스 상태 확인: ./status.sh (있으면)"
