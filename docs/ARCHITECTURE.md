# Agent Architecture and Layout

이제 repo는 아래처럼 단순한 구조로 정리되어 있습니다.

```
/Users/lewis/Desktop/agent/
├── outputs/                 # SQLite + JSON/HTML/CSV/MD 결과 + 텔레그램/피드 설정
├── src/
│   ├── services/
│   │   └── serve_dashboard.py  # 대시보드 서버 + 수동 스크래핑 API
│   ├── watch/
│   │   ├── loop.py            # 주기적 워처 (watch_settings.json 기반)
│   │   └── scraper.py         # 모든 소스(RSS, 웹, Telegram) 수집/TD + 뉴스 저장
│   └── utils/                # DB, 로깅, 알림, 리포터, 스코어링, 설정 등 재사용 코드
├── start_all.sh             # 대시보드 + 워처를 한꺼번에 시작
├── stop_all.sh              # PID를 읽어 대시보드/워처 프로세스 종료
└── logs/                    # stdout/stderr 로그
```

## 실행 포인트
- `python3 src/watch/scraper.py [collect|incremental|daily]` : 단일 스크래핑 실행
- `python3 src/watch/loop.py` : `watch_settings.json`에 정의된 간격으로 스크래퍼를 자동 반복
- `python3 src/services/serve_dashboard.py` : `outputs/`를 노출하는 인터랙티브 대시보드 + 설정/뉴스/실행 API
- `./start_all.sh` / `./stop_all.sh` : 두 서비스를 한꺼번에 켜고 끄는 레벨 쉘 진입

## 목표
1. `src/watch/` 패키지에 수집/스케줄링을 고정하고, `src/services/`에는 대시보드와 API만 두어 코드를 분리했습니다.
2. `outputs/`는 결과물의 단일 쓰기 포인트이며, 대시보드는 해당 디렉터리만 원격에서 읽습니다.
3. `logs/`는 서비스 별로 나뉘므로 `tail -f logs/*.log`으로 전체 상태를 확인할 수 있습니다.

다음 단계로, `src/services/serve_dashboard.py`를 더 작게 나누거나 HTTP 프레임워크를 도입하려면 이 구조를 그대로 유지하면서 각각의 책임(스크래핑 vs. 프론트)을 명확히 분리해 주세요.
