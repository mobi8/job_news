#!/bin/bash

# 모든 서비스를 백그라운드에서 실행

set -e  # 에러 발생 시 중단

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 모든 서비스 시작..."

# 환경 변수 로드
export $(cat .env | xargs)

# 1. 대시보드 서버 (포트 8765)
echo "📊 대시보드 시작 (http://127.0.0.1:8765)..."
python3 src/services/serve_dashboard.py > logs/dashboard.log 2>&1 &
DASHBOARD_PID=$!
echo "   PID: $DASHBOARD_PID"

# 2. 주기적 폴링 (watch_settings.json 기준으로 실행)
echo "👁️  주기적 수집 시작..."
python3 src/watch/loop.py > logs/watch_loop.log 2>&1 &
WATCH_PID=$!
echo "   PID: $WATCH_PID"

# PID 저장 (나중에 중지할 때 사용)
echo "$DASHBOARD_PID" > .pids/dashboard.pid
echo "$WATCH_PID" > .pids/watch.pid

echo ""
echo "✅ 모든 서비스 시작 완료!"
echo ""
echo "📋 실행 중인 프로세스:"
ps aux | grep -E "serve_dashboard|loop\\.py" | grep -v grep
echo ""
echo "📁 로그 파일:"
echo "   - logs/dashboard.log"
echo "   - logs/watch_loop.log"
echo ""
echo "📱 텔레그램 테스트 발송:"
echo "   python3 src/services/telegram_test_loop.py  (필요할 때만 실행)"
echo ""
echo "❌ 모든 서비스 중지하려면: ./stop_all.sh"
echo "👀 로그 확인: tail -f logs/*.log"
