#!/bin/bash

# 서비스 상태 확인

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "📊 서비스 상태 확인"
echo "================================================"
echo ""

# 1. 대시보드 서비스
echo "1. 📊 대시보드 서비스:"
if [ -f ".pids/dashboard.pid" ]; then
    PID=$(cat .pids/dashboard.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "   ✅ 실행 중 (PID: $PID)"
        
        # API 상태 확인
        if curl -s http://127.0.0.1:8765/api/health > /dev/null 2>&1; then
            echo "   ✅ API 응답: http://127.0.0.1:8765/api/health"
            echo "   ✅ 대시보드: http://127.0.0.1:8765/job_stats_dashboard.html"
            
            # 간단한 건강 상태
            HEALTH=$(curl -s http://127.0.0.1:8765/api/health 2>/dev/null | python3 -c "import sys,json; data=json.load(sys.stdin); print(f'상태: {data.get(\"status\", \"unknown\")}')" 2>/dev/null || echo "   ❓ 상태 확인 불가")
            echo "   $HEALTH"
        else
            echo "   ❌ API 응답 없음"
        fi
    else
        echo "   ❌ PID는 있지만 프로세스 없음"
    fi
else
    echo "   ❌ 실행 중이 아님 (PID 파일 없음)"
fi

echo ""

# 2. 워치 서비스
echo "2. 👁️  워치 서비스:"
if [ -f ".pids/watch.pid" ]; then
    PID=$(cat .pids/watch.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "   ✅ 실행 중 (PID: $PID)"
        
        # 마지막 스크래핑 시간 확인
        if [ -f "outputs/scrape_state.json" ]; then
            LAST_SCRAPED=$(cat outputs/scrape_state.json | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('last_scraped_at', '알 수 없음'))" 2>/dev/null || echo "알 수 없음")
            MODE=$(cat outputs/scrape_state.json | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('mode', '알 수 없음'))" 2>/dev/null || echo "알 수 없음")
            echo "   📅 마지막 실행: $LAST_SCRAPED"
            echo "   🎯 모드: $MODE"
        fi
    else
        echo "   ❌ PID는 있지만 프로세스 없음"
    fi
else
    echo "   ❌ 실행 중이 아님 (PID 파일 없음)"
fi

echo ""

# 3. 텔레그램 서비스
echo "3. 📨 텔레그램 서비스:"
if [ -f ".pids/telegram.pid" ]; then
    PID=$(cat .pids/telegram.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "   ✅ 실행 중 (PID: $PID)"
    else
        echo "   ❌ PID는 있지만 프로세스 없음"
    fi
else
    echo "   ❌ 실행 중이 아님 (PID 파일 없음)"
fi

echo ""

# 4. 데이터베이스 상태
echo "4. 🗄️  데이터베이스 상태:"
if [ -f "outputs/jobs.sqlite3" ]; then
    python3 -c "
import sqlite3
from pathlib import Path
import json

db_path = Path('outputs/jobs.sqlite3')
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 작업 개수
    cursor.execute('SELECT COUNT(*) FROM jobs')
    jobs_count = cursor.fetchone()[0]
    
    # 뉴스 개수
    cursor.execute('SELECT COUNT(*) FROM news')
    news_count = cursor.fetchone()[0]
    
    # 최근 24시간
    cursor.execute('''SELECT COUNT(*) FROM jobs WHERE datetime(first_seen_at) > datetime('now', '-24 hours')''')
    recent_jobs = cursor.fetchone()[0]
    
    cursor.execute('''SELECT COUNT(*) FROM news WHERE datetime(published_at) > datetime('now', '-24 hours')''')
    recent_news = cursor.fetchone()[0]
    
    conn.close()
    
    print(f'   📊 채용 공고: {jobs_count}개 (최근 24시간: {recent_jobs}개)')
    print(f'   📰 뉴스 기사: {news_count}개 (최근 24시간: {recent_news}개)')
    
    # 스크래핑 상태
    state_path = Path('outputs/scrape_state.json')
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
        new_jobs = state.get('new_jobs_this_run', 0)
        print(f'   🆕 최근 스크래핑 신규: {new_jobs}개')
else:
    print('   ❌ 데이터베이스 파일 없음')
" 2>/dev/null || echo "   ❓ 데이터베이스 확인 불가"
else
    echo "   ❌ 데이터베이스 파일 없음"
fi

echo ""
echo "================================================"
echo "📋 모든 프로세스 목록:"
echo "------------------------------------------------"
ps aux | grep -E "serve_dashboard|loop\.py|telegram" | grep -v grep || echo "   실행 중인 서비스가 없습니다"

echo ""
echo "📁 로그 파일 크기:"
echo "------------------------------------------------"
ls -lh logs/*.log 2>/dev/null | awk '{print "   "$5" "$9}' || echo "   로그 파일 없음"

echo ""
echo "🔄 서비스 관리:"
echo "   시작: ./start_all.sh"
echo "   중지: ./stop_all.sh"
echo "   상태: ./status.sh"