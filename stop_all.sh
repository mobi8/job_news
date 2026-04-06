#!/bin/bash

# 모든 서비스 중지

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🛑 모든 서비스 중지 중..."

# PID 파일에서 프로세스 ID 읽기
if [ -f ".pids/dashboard.pid" ]; then
    PID=$(cat .pids/dashboard.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        echo "✓ 대시보드 중지 (PID: $PID)"
    fi
fi

if [ -f ".pids/watch.pid" ]; then
    PID=$(cat .pids/watch.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        echo "✓ 주기적 수집 중지 (PID: $PID)"
    fi
fi


# 혹시 남은 프로세스 확인
echo ""
echo "남은 프로세스 확인:"
ps aux | grep -E "serve_dashboard|loop\\.py" | grep -v grep || echo "실행 중인 프로세스 없음"
