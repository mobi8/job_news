# 배치 작업 가이드

## 개요

이 시스템은 **3가지 배치 모드**를 안전하게 관리합니다:

| 모드 | 설명 | 주기 | 시간 |
|------|------|------|------|
| `collect` | 전체 소스 완전 수집 | 24시간 | ~30분 |
| `incremental` | 신규 공고만 빠르게 수집 | 3시간 | ~5분 |
| `daily` | 최근 24시간 분석 + AI 인사이트 | 24시간 | ~10분 |

## 실행 방법

### 1. 전체 배치 실행 (권장)
```bash
python3 batch_scheduler.py
```
→ 3가지 작업을 순서대로 안전하게 실행 (collect → incremental → daily)

### 2. 특정 작업만 실행
```bash
python3 batch_scheduler.py collect      # 전체 수집
python3 batch_scheduler.py incremental  # 신규만 수집
python3 batch_scheduler.py daily        # 일일 분석
```

### 3. 스크래퍼 직접 실행 (고급)
```bash
python3 scraper.py collect    # collect 모드
python3 scraper.py daily      # daily 모드
```

## 안전 메커니즘

### 1. 작업 중복 방지
- 한 번에 하나의 작업만 실행
- `/tmp/agent_batch.lock` 파일로 관리
- 1시간 이상 경과 시 자동 락 해제 (데드락 방지)

### 2. 실행 간격 보장
```
마지막 실행 이후:
- collect: 24시간 경과 후 재실행
- incremental: 3시간 경과 후 재실행
- daily: 24시간 경과 후 재실행
```

### 3. 타임아웃 설정
```
- collect: 1800초 (30분)
- incremental: 300초 (5분)
- daily: 600초 (10분)
```
→ 예상 시간 + 50% 여유 시간 포함

### 4. 작업 간 지연
- 각 작업 사이 5초 대기
- 시스템 과부하 방지

## 서비스 상태 확인

```bash
# 텍스트 출력
python3 services_status.py

# JSON 포맷
python3 services_status.py json
```

**상태 항목:**
- ✓ OpenRouter API (AI 인사이트) - 선택사항
- ✓ Telegram 알림 - 선택사항
- ✓ RSS 피드 스크래핑 - 필수
- ✓ 브라우저 자동화 - 필수
- ✓ SQLite 데이터베이스 - 필수
- ✓ 대시보드 HTTP 서버 - 필수

## 자동 실행 (cron)

### 방법 1: 메인 배치만 유지
```bash
# 메인 워처는 기존 `src/watch/loop.py` 또는 `run_dashboard.sh` 흐름을 그대로 유지
```

### 방법 2: incremental을 더 자주 실행
```bash
# 3시간마다
0 */3 * * * cd /Users/lewis/Desktop/agent && python3 batch_scheduler.py incremental >> /tmp/agent_batch.log 2>&1
```

## 로그 확인

```bash
# 실시간 로그 모니터링
tail -f /tmp/agent_batch.log

# 최근 50줄 확인
tail -50 /tmp/agent_batch.log

# 에러만 필터링
grep ERROR /tmp/agent_batch.log
```

## 문제 해결

### 작업이 실행되지 않음
```bash
# 1. 락 파일 확인
ls -la /tmp/agent_batch.lock

# 2. 락 파일 강제 제거 (필요 시)
rm -f /tmp/agent_batch.lock

# 3. 마지막 실행 시간 확인
cat outputs/scrape_state.json | jq .last_at
```

### 타임아웃 발생
→ 네트워크 문제일 가능성. collect 모드에서는 30분까지 가능합니다.

### Telegram 알림이 안 옴
→ `.env` 파일에서 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 확인

## 배치 실행 시나리오

### 일반적인 운영
```
메인 워처:    python3 src/watch/loop.py
              (Glassdoor 제외, 나머지 소스는 계속 수집)

Glassdoor:    ./run_glassdoor.sh
              (수동 실행 전용)
```

### 첫 실행 (Cold Start)
```bash
python3 batch_scheduler.py  # 전체 배치
# 완료 후 대시보드 접속: http://127.0.0.1:8765
```

## 데이터 흐름

```
Raw Sources (8 sources)
    ↓
    ├─ [collect] 전체 수집 + DB 저장
    ├─ [incremental] 신규 필터링 + DB 업데이트
    └─ [daily] 분석 + AI 인사이트 + Telegram 발송
    ↓
Database (jobs.sqlite3)
    ↓
Dashboard Data (job_stats_data.json)
    ↓
Visualization (http://127.0.0.1:8765)
```

## 성능 최적화

- **AI 인사이트**: 24시간 파일 캐싱으로 API 호출 최소화
- **DB 쿼리**: 인덱싱 완료 (source_job_id)
- **스크래핑**: 병렬 처리 (RSS) + Playwright headless (브라우저)
- **Glassdoor**: 수동 실행 전용으로 분리

---

**마지막 업데이트:** 2026-03-29
