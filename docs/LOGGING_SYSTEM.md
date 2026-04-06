# 로깅 시스템 가이드

## 개요

모든 모듈에서 **구조화된 JSON 로깅**을 사용합니다. 로그는 자동으로 회전되며, 타임스탐프, 레벨, 모듈명이 포함됩니다.

## 로그 위치

| 파일 | 모듈 | 용도 |
|------|------|------|
| `logs/watch_loop.log` | job_watch_loop.py | 주기적 수집 루프 |
| `logs/dashboard.log` | serve_dashboard.py | 대시보드 서버 & HTTP 요청 |
| `logs/scraper.log` | scraper.py | 스크래퍼 실행 로그 |
| `logs/notifications.log` | notifications.py | Telegram 알림 발송 |
| `logs/database.log` | db.py | 데이터베이스 작업 |

## 로그 포맷

모든 로그는 **JSON** 형식입니다:

```json
{
  "timestamp": "2026-04-03T09:21:46.405741",
  "level": "INFO",
  "module": "watch_loop",
  "message": "Running watcher (mode=daily, interval=3600s)",
  "line": 42
}
```

**필드 설명:**
- `timestamp` — ISO 8601 형식의 시간
- `level` — 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `module` — 로거 이름 (모듈 식별)
- `message` — 상세 메시지
- `line` — 로그를 호출한 코드 라인 번호

## 로그 확인

### 실시간 모든 로그 확인
```bash
tail -f logs/*.log
```

### 특정 모듈만 확인
```bash
tail -f logs/watch_loop.log        # 주기 수집
tail -f logs/dashboard.log         # 대시보드
tail -f logs/scraper.log           # 스크래퍼
```

### JSON 파싱하여 필터링 (고급)
```bash
# INFO 레벨만 보기
tail -f logs/*.log | grep '"level": "INFO"'

# 특정 모듈만 보기
tail -f logs/*.log | grep '"module": "scraper"'

# 마지막 20줄
tail -20 logs/watch_loop.log
```

## 로그 로테이션

- **자동 회전**: 파일이 **10MB**를 초과하면 자동으로 회전
- **백업 보관**: 최근 **5개 백업** 파일 유지 (`*.log.1`, `*.log.2`, ...)
- **자동 정리**: 오래된 백업은 자동으로 삭제

예:
```
logs/watch_loop.log       # 현재 (< 10MB)
logs/watch_loop.log.1     # 1회차 백업
logs/watch_loop.log.2     # 2회차 백업
...
logs/watch_loop.log.5     # 5회차 백업
```

## 코드에서 로깅 사용하기

### 1. 모듈에서 로거 임포트
```python
from utils.logger import scraper_logger

# 또는 모듈별로:
# from utils.logger import watch_logger
# from utils.logger import dashboard_logger
# from utils.logger import notifications_logger
```

### 2. 로그 작성
```python
# INFO 레벨
scraper_logger.info(f"Collected {count} jobs from {source}")

# DEBUG 레벨 (파일에만 저장, 콘솔에 미출력)
scraper_logger.debug(f"Processing job: {job_id}")

# WARNING 레벨
scraper_logger.warning(f"Slow response from {url}")

# ERROR 레벨
scraper_logger.error(f"Failed to parse: {error_msg}")

# CRITICAL 레벨
scraper_logger.critical(f"Database connection lost")
```

### 3. 예외 로깅
```python
try:
    result = process_job(job)
except Exception as e:
    scraper_logger.error(f"Error processing job: {str(e)}")
    # 또는 스택 트레이스 포함
    scraper_logger.exception(f"Detailed error: {str(e)}")
```

## 로그 레벨별 가이드

| 레벨 | 콘솔 출력 | 파일 저장 | 용도 |
|------|---------|--------|------|
| DEBUG | ❌ | ✅ | 상세한 디버깅 정보 |
| INFO | ✅ | ✅ | 정상 진행 상황 (기본) |
| WARNING | ✅ | ✅ | 주의 필요한 상황 |
| ERROR | ✅ | ✅ | 오류 발생 |
| CRITICAL | ✅ | ✅ | 시스템 심각 오류 |

**콘솔 출력**: INFO 레벨 이상만 표시
**파일 저장**: 모든 레벨 저장

## 로거 추가하기 (신규 모듈)

### 1. logger.py에 등록
```python
# src/utils/logger.py에 추가
my_module_logger = setup_logger("my_module", "my_module.log", json_format=True)
```

### 2. 모듈에서 사용
```python
# src/my_module.py
from utils.logger import my_module_logger

my_module_logger.info("Message here")
```

## 성능 고려사항

- **JSON 포맷**: 자동 파싱 가능, 약간의 오버헤드 (무시할 수준)
- **파일 회전**: 10MB 단위로 자동 정리 (디스크 사용 최소화)
- **콘솔 필터링**: INFO 레벨만 콘솔에 출력 (노이즈 감소)
- **파일 저장**: 모든 레벨 저장으로 나중에 분석 가능

## 문제 해결

### 로그가 너무 길어짐
- `logs/` 폴더 크기 확인: `du -sh logs/`
- 로그 파일 정리: `rm -f logs/*.log.*` (백업만 삭제)
- 또는 자동 회전 설정 확인: `logger.py`의 `maxBytes=10*1024*1024`

### 로그가 저장되지 않음
- 파일 권한 확인: `ls -la logs/`
- `logs/` 디렉토리 존재 확인
- 코드에서 올바른 로거 임포트 확인

### 로그 검색
```bash
# "error" 단어가 포함된 로그
grep -i "error" logs/*.log

# 특정 시간 범위의 로그
grep "2026-04-03T09:2" logs/*.log

# JSON 파싱하여 특정 모듈만
grep '"module": "scraper"' logs/*.log
```

## 통합 모니터링 (선택 사항)

향후 확장 가능:
- ELK Stack (Elasticsearch, Logstash, Kibana) 연동
- CloudWatch 같은 클라우드 로깅 서비스
- 실시간 알림 (로그에 ERROR 발생 시 Telegram 알림)

현재는 파일 로깅만 구현되어 있습니다.
