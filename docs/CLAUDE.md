# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

UAE/GCC 지역의 암호화폐·핀테크·iGaming 관련 포지션을 자동으로 수집·분석하는 개인 구직 자동화 엔진. 8개 이상의 채용 소스에서 공고를 스크래핑하고, 키워드 렉시콘 기반으로 매칭 점수를 산출해 SQLite에 저장하며, 인터랙티브 HTML 대시보드로 제공한다. 정해진 시간별로 배치를 돌려서 스크랩을 하고 텔레그램으로 알림을 보내줘 알림은 기사와, 공고를 보내줘

## 명령어

### 초기 설정
```bash
npm install           # playwright-core 설치 (유일한 외부 의존성)
cat > resume.md << 'EOF'
# Professional Background
...
EOF
```

### 스크래퍼 실행 (src/core/scraper.py)
```bash
python3 src/core/scraper.py collect       # 전체 소스 전체 수집
python3 src/core/scraper.py incremental   # 마지막 실행 이후 신규 공고만 수집
python3 src/core/scraper.py daily         # 최근 24시간 내 공고 + 뉴스 분석
```

### 시스템 시작/중지 (추천)
```bash
./start_all.sh  # 대시보드 + job_watch_loop 동시 실행
./stop_all.sh   # 모든 서비스 중지
```

### 개별 서비스 실행 (고급)
```bash
python3 src/core/job_watch_loop.py         # 주기적 폴링 (60분 간격)
python3 src/services/serve_dashboard.py    # 대시보드 http://127.0.0.1:8765
python3 src/services/telegram_test_loop.py # 텔레그램 테스트 (한 번만)
```

### 배치 스케줄링 (선택 사항)
```bash
python3 src/core/batch_scheduler.py  # 안전한 순차 배치 (충돌 방지)
```

### 데이터베이스 정리 및 재채점
```bash
python3 src/core/db_cleanup_and_rescore.py  # 오래된 공고 삭제 + 미채점 공고 재채점
python3 src/core/db_rescore_direct.py       # 직접 SQLite 재채점 (더 빠름)
```

### 테스트
```bash
pytest                          # 모든 테스트 실행 (217개)
pytest tests/test_db.py         # 특정 파일만 테스트
pytest tests/test_scoring.py -v # 상세 출력과 함께 실행
pytest -k "fingerprint"         # 특정 테스트만 실행 (이름으로 필터)
pytest -x                       # 첫 실패에서 중단
```

### 환경 변수
- **텔레그램**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — 알림용
- **뉴스 & AI**: `ANTHROPIC_API_KEY` — Claude API (선택 사항)
- **스크래핑**: `WATCH_WINDOW_HOURS` (기본 3h), `JOB_WATCH_SOURCES` (쉼표 구분)

## 아키텍처

### 모듈 구조
이전 monolithic `linkedin_job_scraper.py` (3,750줄)를 8개 모듈로 분리 완료 (2026-03-28):

| 모듈 | 책임 | 규모 |
|------|------|------|
| `config.py` | 상수, URL, 매칭 렉시콘 | 100줄 |
| `models.py` | `JobPosting`, `NewsItem` 데이터클래스 | 50줄 |
| `db.py` | SQLite 래퍼, CRUD + 집계 | 250줄 |
| `scrapers.py` | 8개 채용 소스 파싱 + RSS 피드 | 800줄 |
| `scoring.py` | 점수 산출, 필터링 로직 | 400줄 |
| `reporter.py` | JSON/CSV/MD 저장, HTML 대시보드 생성 | 1,550줄 |
| `notifications.py` | Telegram 메시지, 소스별 카운트 | 280줄 |
| `utils.py` | 헬퍼 함수 (reject_feedback 로드 등) | 150줄 |
| `scraper.py` (엔진) | run() + main() 진입점 | 250줄 |

### 데이터 흐름
```
[8개 채용 소스] ──┐
[RSS 뉴스 피드] ─┼→ [scrapers.py] ──→ [scoring.py] ──→ [db.py] ──→ [reporter.py] ──→ [outputs/]
[Telegram 채널] ─┘                   (점수/필터)      (저장)      (JSON/CSV/MD)

[job_watch_loop.py] (60분 간격)
   └─→ scraper.py "daily" 모드 ──→ [notifications.py] ──→ Telegram 알림

[batch_scheduler.py] (수동 실행)
   └─→ collect (24h) → incremental (3h) → daily (24h)
      ├─ Lock 파일로 중복 실행 방지
      └─ 각 task별 timeout으로 시간초과 보호
```

### 핵심 파일별 인터페이스

**`scrapers.py`** — 8개 채용 소스
- HTML 스크래핑 (urllib + 정규식): Jobvite, SmartRecruitment, iGaming Recruitment, Jobrapido, JobLeads, Telegram 채널
- 브라우저 자동화 (Playwright): Indeed UAE, LinkedIn
- RSS 피드: `fetch_all_rss_news()`, `fetch_all_player_rss_news()`
- 반환: `List[JobPosting]`, `List[NewsItem]`

**`scoring.py`** — 매칭 엔진
- `calculate_match_score(job, resume_text)` → 0~100점
- 필터: `is_language_filtered_out()`, `is_hard_excluded_job()`, `matches_reject_feedback()`
- 최상위: `top_recommendations(jobs, limit=10)`
- 주요 수정점: `config.py`의 `FOCUS_DOMAIN_TERMS`, `STRONG_DOMAIN_TERMS`, `HARD_EXCLUDE_*` 렉시콘

**`db.py`** — SQLite 저장소
- 쓰기: `upsert_jobs(jobs)`, `upsert_news(news_items)`
- 읽기: `fetch_all_jobs()`, `fetch_recent_news()`, `jobs_first_seen_since(hours)`
- 통계: `source_total_counts()`, `source_new_counts(hours)`, `stats()`
- 정리: `purge_*(filters)` — 중복 제거, 필터 적용
- 중복 감지: SHA1(title+company+location) 지문 기반

**`notifications.py`** — Telegram 통보
- `send_daily_summary(jobs)` — 신규 공고 요약
- `send_news_summary(news_items)` — 뉴스 요약
- `source_*_counts()` — 소스별 통계 계산

**`reporter.py`** — 출력 생성
- `save_json()`, `save_csv()`, `save_markdown()` → outputs/
- `save_dashboard()` → HTML 생성 (JS 포함)
- `save_dashboard_data()` → JSON 메타데이터

### 출력물 (`outputs/` 디렉토리)
| 파일 | 용도 |
|------|------|
| `jobs.sqlite3` | 중복 제거된 공고 영구 저장소 |
| `jobs_analysis.json` | 전체 구조화 결과 (job_stats_data.json에 ai_insights도 포함) |
| `jobs_recommendations.csv` | 상위 10개 매칭 공고 |
| `jobs_analysis.md` | 사람이 읽기 쉬운 리포트 |
| `job_stats_dashboard.html` | 인터랙티브 대시보드 (serve_dashboard.py로 제공) |
| `watch_settings.json` | 스크래핑 주기 설정 |
| `reject_feedback.json` | 사용자 정의 제외 패턴 |
| `scrape_state.json` | 마지막 실행 메타데이터 |

### 주요 설계 패턴
- **중복 제거** — SHA1(title+company+location) 지문으로 공고 식별; `upsert_jobs()`가 재발견 시 `last_seen_at` 갱신
- **플러그인식 소스** — 각 소스는 독립적인 파싱 함수; 새 소스 추가 시 `scrapers.py`에 파서만 추가하면 됨
- **단순 알림 흐름** (2026-03-30 정리):
  - `job_watch_loop.py` (60분) → `scraper.py daily` 1회 호출 → 필요 시 Telegram 1~2개 메시지만 발송
  - 이전의 중복 알림 로직 제거됨
- **뉴스 & AI 인사이트** (선택 사항):
  - `fetch_all_rss_news()` + `fetch_all_player_rss_news()` → `NewsItem` 객체
  - `ANTHROPIC_API_KEY` 있으면 Claude로 5가지 인사이트 생성 (시장 임팩트, 위기, 기회, 나에 대한 임팩트, 토론 주제)
  - Fingerprint 캐싱으로 중복 API 호출 방지
- **대시보드 API** — `serve_dashboard.py`가 `/run-scrape`, `/watch-settings`, `/reject-feedback`, `/api/recent-news` POST/GET 요청 처리
- **매칭 렉시콘** — `config.py`의 `FOCUS_DOMAIN_TERMS`, `STRONG_DOMAIN_TERMS`, `HARD_EXCLUDE_TITLE_TERMS` 수정으로 점수 튜닝

## 최근 변경사항 (2026-03-28~04-03)

### 모듈화 완료 (2026-03-28)
- 3,750줄 monolithic 파일 → 8개 모듈로 분리
- 각 모듈은 단일 책임 원칙 준수

### 배치/알림 정리 (2026-03-30)
- `job_watch_loop.py`의 중복 알림 로직 제거
- `notifications.py` 미사용 함수 5개 제거 (342줄 → 281줄)
- **뉴스 발송 최적화**: daily 모드에서만 발송 (60분마다 중복 메시지 방지)
- 명확한 흐름: daily 모드 1회 실행 = Telegram 1~2개 메시지만

### 점수 계산 문제 해결 (2026-03-30)
- **문제**: LinkedIn 공고 1,340개가 score=0 (미채점)
- **원인**:
  - resume 파일 없음 (기본값 inferred_profile 사용)
  - `COMMERCIAL_ROLE_TERMS`에 "engineer", "architect" 없음
  - `NON_COMMERCIAL_ROLE_TERMS`에 있어서 페널티 (-22점)
- **해결**:
  - ✅ `resume.md` 파일 생성 (점수 계산 기준)
  - ✅ `COMMERCIAL_ROLE_TERMS`에 "engineer", "architect" 추가
  - ✅ `NON_COMMERCIAL_ROLE_TERMS`에서 제거
  - ✅ `db_cleanup_and_rescore.py`, `db_rescore_direct.py` 추가

### 데이터베이스 정리 (2026-03-30)
- 160개 오래된 공고 삭제 (3일 이상 미업데이트)
- 1,417개 미채점 공고 재채점
- 최종 상태: 1,954개 공고, avg_score=6.6

### start_all.sh 개선 (편의 기능)
```bash
# 대시보드 + job_watch_loop 동시 실행
./stop_all.sh   # 모든 서비스 중지
```
- telegram_test_loop은 자동 실행에서 제거 (필요할 때만 수동 실행)

### 구조화된 로깅 시스템 구현 (2026-04-03)
- `src/utils/logger.py` 신규 생성 (중앙화된 로거 설정)
- 모든 모듈에서 **JSON 형식** 로깅 적용
  - `job_watch_loop.py`: print() → logger.info/debug/error
  - `serve_dashboard.py`: HTTP 요청 로깅 + 비즈니스 로직 로깅
  - `scraper.py`, `notifications.py`: 기존 logging → 중앙 logger
- **로그 로테이션**: 10MB 초과 시 자동 회전, 5개 백업 유지
- **로그 레벨**: DEBUG (파일만), INFO, WARNING, ERROR, CRITICAL
- 자세한 내용: [LOGGING_SYSTEM.md](LOGGING_SYSTEM.md) 참고

## 테스트 (217개 테스트)

### 테스트 구조
```
tests/
├── test_db.py (45+ 테스트) — Database CRUD, upsert, purge, 통계
├── test_db_update.py (3 테스트) — Upsert 업데이트, 오래된 공고 감지
├── test_linkedin_scoring.py (5 테스트) — LinkedIn 공고 점수 계산
├── test_message_debug.py (5 테스트) — Telegram 메시지 발송 조건
├── test_models.py (35 테스트) — JobPosting, NewsItem 데이터클래스
├── test_notifications.py (35+ 테스트) — Telegram 메시지 생성
├── test_score_debug.py (1 테스트) — 점수 계산 디버깅
├── test_scoring.py (50+ 테스트) — 점수 산출, 필터링, 렉시콘
├── test_utils.py (30+ 테스트) — 헬퍼 함수
└── conftest.py — pytest 설정 (src/ 경로 추가)
```

### 실행
```bash
pytest                           # 모든 테스트
pytest tests/test_db.py -v       # 상세 출력
pytest -k "fingerprint"          # 특정 테스트 필터
pytest -x                        # 첫 실패에서 중단
```

각 테스트는 edge case, boundary condition, error handling을 포함.

## 운영 가이드

### 서비스 관리
**모든 서비스 시작**
```bash
./start_all.sh
```
- 📊 대시보드 (http://127.0.0.1:8765)
- 👁️ job_watch_loop (60분 간격 수집)
- 자동으로 `.pids/` 디렉토리에 PID 저장

**모든 서비스 중지**
```bash
./stop_all.sh
```
- `.pids/`의 저장된 PID로 프로세스 중지
- 프로세스가 이미 종료됐으면 경고 없음

**로그 확인** (자세한 내용은 [LOGGING_SYSTEM.md](LOGGING_SYSTEM.md) 참고)
```bash
tail -f logs/*.log              # 실시간 모든 로그
tail -f logs/dashboard.log      # 대시보드 로그만
tail -f logs/watch_loop.log     # 수집 루프 로그만
```

모든 로그는 **JSON 형식**이며 자동으로 **10MB 단위로 회전**됩니다. 타임스탐프와 로그 레벨이 자동으로 포함됩니다.

**텔레그램 테스트 메시지 (한 번만)**
```bash
python3 src/services/telegram_test_loop.py
```
- 현재 상위 공고 5개를 텔레그램으로 발송
- 루프 없음 (한 번 실행 후 종료)

## 개발 가이드

### 새 채용 소스 추가 (Scraper)
1. `scrapers.py`에 `parse_<source_name>_jobs(raw_html: str) -> List[JobPosting]` 함수 작성
2. URL을 `config.py`의 `<SOURCE>_URL` 상수로 정의
3. `scraper.py`의 `run()` 함수에서 호출 추가 (필요 시 `fetch_html()` 사용)
4. 점수 계산은 자동으로 `calculate_match_score()`가 담당

### resume.md 설정
점수 계산의 기준이 되는 사용자 이력서 파일. 수정하면 점수 가중치 변경:

```bash
# 위치: /Users/lewis/Desktop/agent/resume.md
# 내용: 기술 스택, 관심사, 목표 직무 등
# 변경 후: ./start_all.sh 재시작하면 다음 스크래핑부터 적용
```

### 매칭 렉시콘 튜닝
`config.py`의 다음 상수 수정:
- `COMMERCIAL_ROLE_TERMS` — +14점 (관심 직무): "engineer", "architect", "product manager", "account manager" 등
  - 2026-03-30: "engineer", "architect" 추가 (LinkedIn 공고 점수 계산)
- `FOCUS_DOMAIN_TERMS` — +30점 (핵심 도메인): "web3", "crypto", "fintech", "igaming", "neobank" 등
- `STRONG_DOMAIN_TERMS` — +48점 최대 (강한 매칭): FOCUS_DOMAIN_TERMS의 상위집합
- `HARD_EXCLUDE_TITLE_TERMS` — 완전 제외: "Sales", "Presenter" 등
- `NON_COMMERCIAL_ROLE_TERMS` — 패널티 (-22점): "compliance", "legal", "operations" 등
  - 2026-03-30: "engineer", "developer", "architect" 제거

### 데이터베이스 정리
```bash
# 오래된 공고 삭제 + 미채점 공고 재채점
python3 src/core/db_cleanup_and_rescore.py

# 또는 직접 SQLite 쿼리로 재채점 (더 빠름)
python3 src/core/db_rescore_direct.py
```

언제 실행할 것:
- score=0인 공고가 많을 때
- resume.md를 수정한 후 점수를 다시 계산하고 싶을 때
- 3일 이상 업데이트되지 않은 공고를 정리하고 싶을 때

### 필터 추가
`scoring.py`에 새 필터 함수 작성 후, `run()` 함수의 `annotate_records()` 호출 시 적용:
```python
def is_new_filter(job: JobPosting) -> bool:
    # 로직...
    return should_exclude
```

테스트 작성:
```bash
# tests/test_scoring.py에 테스트 추가
pytest tests/test_scoring.py -v
```

### Telegram 알림 커스터마이징
`notifications.py`에 새 함수 추가 후:
1. 함수명은 `send_*` 패턴
2. `job_watch_loop.py`나 `scraper.py`에서 호출
3. 중복 호출 방지: 같은 조건이면 한 번만 호출하도록 설계

### 대시보드 기능 추가
`serve_dashboard.py`에서:
1. GET 엔드포인트: `/api/<resource>` → JSON 반환
2. POST 엔드포인트: `/api/<resource>` → 설정 업데이트
3. HTML 생성: `reporter.py`의 `save_dashboard()` 수정 후 JS 추가

### 환경변수 확인
- 개발: `TELEGRAM_BOT_TOKEN` 없어도 작동 (경고만 출력)
- CI: `pytest`는 환경변수 불필요 (mock 사용)
- 운영: `.env` 파일에 실제 토큰 입력

### 의존성 관리
- **유일한 외부 의존성**: `playwright-core` (npm으로 설치)
- Python stdlib만 사용 (urllib, sqlite3, json, logging 등)
- 테스트: `pytest` 필수, `pytest-cov` 선택 사항

### 성능 최적화 팁
- **스크래퍼**: `fetch_html()` timeout 5초 (느린 사이트 건너뜀)
- **데이터베이스**: SHA1 지문 기반 upsert로 중복 검사 O(1)
  - `upsert_jobs()`: 중복 공고면 `last_seen_at` 갱신만 수행
  - `jobs_first_seen_since()`: 특정 시간 이후 신규 공고 조회 (인덱스 활용)
- **알림**: Sent history로 중복 발송 방지
  - `telegram_sent_history.json`: 발송한 공고/뉴스 URL 기록
  - 7일마다 자동 정리 (prune_telegram_sent_history)
- **AI 인사이트**: Fingerprint 캐싱으로 같은 뉴스 목록이면 API 호출 안 함
- **Batch scheduler**: Lock 파일로 동시 실행 방지 (각 task 최대 30분 timeout)

### 디버깅 팁
- LinkedIn 공고 점수 확인: `pytest tests/test_linkedin_scoring.py -v`
- DB 상태 분석: `sqlite3 outputs/jobs.sqlite3` → SQL 쿼리
- 뉴스 발송 조건: `pytest tests/test_message_debug.py -v`
- 점수 계산 과정: `python3 src/core/db_rescore_direct.py` (로그 확인)

### 로깅 추가하기
새 모듈에서 로깅을 사용하려면:
1. `logger.py`에 로거 등록: `my_module_logger = setup_logger("my_module", "my_module.log", json_format=True)`
2. 모듈에서 임포트: `from utils.logger import my_module_logger`
3. 로그 작성: `my_module_logger.info("메시지")`

모든 로그는 자동으로 JSON 형식으로 저장되며 파일 크기 초과 시 자동 회전됩니다.
