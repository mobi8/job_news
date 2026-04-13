# Job Watch API

`scripts/watch/scraper.py`에서 생성하는 `outputs/jobs_analysis.json` 및 `outputs/job_stats_data.json`를 기반으로 JS/TS 프론트엔드가 읽을 수 있는 REST API를 제공합니다.

## 실행
- 의존성 설치: `pip install -r requirements.txt`
- API 서버 실행: `uvicorn src.api.app:app --reload`
- 기본 포트: 8000 (`http://127.0.0.1:8000`)

## 주요 엔드포인트

### `GET /api/jobs`
공고 테이블(기존 Dashboard Inbox)용 데이터.

쿼리 파라미터:
- `source`: `linkedin_public`, `indeed_uae`, `telegram_job_crypto_uae` 등 필터.
- `country`: `UAE`, `Georgia`, `Malta` 등.
- `q`: 제목/회사/지역/description 텍스트 검색.
- `qualifies`: `true`/`false`.
- `min_score`, `max_score`: 0–100.
- `limit` (기본 50), `offset`.

응답 예:
```json
{
  "total": 120,
  "limit": 50,
  "offset": 0,
  "jobs": [...],
  "counts": {
    "recommended": 42,
    "non_recommended": 78
  }
}
```

### `GET /api/stats`
통계값, 소스별 누적/일별 건수, 최신 갱신 시간을 반환합니다.

응답 필드: `stats`, `source_total`, `source_daily`, `updated_at`, `collection_metadata`.

### `GET /api/recommendations`
추천 슬롯(상단 Top Picks / Telegram 미리보기)의 `top_recommendations`.

쿼리: `limit` (기본 10, 최대 50).

### `GET /api/news`
`job_stats_data.json`에 저장된 `news_items` (소스별 메타 포함).

### `GET /api/topics`
`compute_news_topics()`에서 생성한 `topics`.

### `GET /api/player-mentions`
`player_mentions` 딕셔너리 (`player name → {category, count, latest_date, articles}`).

### `GET /healthz`
`jobs_analysis.json` / `job_stats_data.json`가 있으면 200, 없으면 503 반환.

## 사용 팁
- 모든 엔드포인트는 scraper가 데이터를 갱신할 때마다 JSON 파일을 다시 읽어 최신 상태를 제공합니다.
- `source_label()` 결과는 `source_label` 필드를 기본으로 채워주므로 프론트엔드에서 직접 라벨 테이블을 다시 만들 필요가 없습니다.
