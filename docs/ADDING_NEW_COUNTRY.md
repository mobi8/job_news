# 새로운 검색 국가 추가 가이드

이 문서는 UAE Job Watcher 시스템에 새로운 검색 국가를 추가하는 방법을 설명합니다.

## 개요

시스템은 다음과 같은 구성 요소로 이루어져 있습니다:
1. **위치 용어 정의** (`config.py`)
2. **검색 URL 추가** (`config.py`) 
3. **스코어링 로직 업데이트** (`scoring.py`)
4. **크롤러 업데이트** (`scrapers.py`)
5. **소스 라벨링 업데이트** (`scoring.py`)

## 단계별 추가 가이드

### 1. 위치 용어 추가 (`src/utils/config.py`)

#### A. `FOCUS_LOCATION_TERMS`에 추가
```python
FOCUS_LOCATION_TERMS = [
    # 기존 항목들...
    "new_country",           # 새 국가 영어명
    "capital_city",          # 수도
    "major_city",           # 주요 도시
    "새국가",               # 한국어명 (선택사항)
]
```

#### B. `REMOTE_GCC_LOCATION_TERMS`에 추가 (원격 근무 고려 시)
```python
REMOTE_GCC_LOCATION_TERMS = [
    # 기존 항목들...
    "new_country",           # 새 국가
    "capital_city",
    "major_city",
]
```

### 2. 검색 URL 추가 (`src/utils/config.py`)

#### A. Indeed 검색 URL 추가 (`INDEED_SEARCH_URLS`)
```python
INDEED_SEARCH_URLS = [
    # 기존 URL들...
    
    # 새 국가 Indeed 검색 URL
    "https://{country_code}.indeed.com/jobs?q=crypto+OR+web3+OR+blockchain+OR+igaming+OR+casino+OR+payment&l={country_name}&sort=date",
    "https://{country_code}.indeed.com/jobs?q=product+manager+OR+product+owner+OR+business+development+OR+sales&l={capital_city}&sort=date",
]
```

**참고**: `{country_code}`는 Indeed 국가 도메인 코드 (예: 'ae'는 UAE, 'ge'는 조지아)
**참고**: `{country_name}`은 국가명, `{capital_city}`는 수도명

#### B. LinkedIn 검색 URL 추가 (`LINKEDIN_SEARCH_URLS`)
```python
LINKEDIN_SEARCH_URLS = [
    # 기존 URL들...
    
    # 새 국가 LinkedIn 검색 URL
    "https://www.linkedin.com/jobs/search/?keywords=crypto%20OR%20web3%20OR%20blockchain%20OR%20igaming%20OR%20casino%20OR%20payment&location={Country Name}",
    "https://www.linkedin.com/jobs/search/?keywords=product%20manager%20OR%20product%20owner%20OR%20business%20development%20OR%20sales&location={Capital City}%2C%20{Country Name}",
    "https://www.linkedin.com/jobs/search/?keywords=backend%20OR%20engineer%20OR%20developer%20OR%20software&location={Country Name}",
]
```

#### C. Jobrapido URL 추가 (선택사항)
```python
# Jobrapido는 국가별 하위 도메인이 없는 경우가 많음
JOBRAPIDO_URL_{COUNTRY} = "https://{country_code}.jobrapido.com/?w=igaming+OR+crypto&l={country_name}&r=&shm=all"
```

### 3. 스코어링 로직 업데이트 (`src/utils/scoring.py`)

#### A. 위치 점수 추가 (`evaluate_fit` 함수)
```python
# 점수 계산 부분에서 새 국가 점수 추가
if "new_country" in text_blob or "capital_city" in text_blob:
    score += 20  # 적절한 점수 설정 (UAE 32점, 조지아 20점 참고)
```

### 4. 크롤러 업데이트 (`src/utils/scrapers.py`)

#### A. Indeed 크롤러 업데이트 (`fetch_indeed_jobs_via_browser` 함수)
```python
# URL에 따라 소스 구분 로직 추가
source_name = "indeed_uae"
if "new_country_code.indeed.com" in search_url or "new_country" in search_url.lower():
    source_name = "indeed_new_country"
```

#### B. LinkedIn 크롤러 업데이트 (`fetch_linkedin_jobs_via_browser` 함수)
```python
# URL에 따라 소스 구분 로직 추가
source_name = "linkedin_public"
if "new_country" in search_url.lower() or "capital_city" in search_url.lower():
    source_name = "linkedin_new_country"
```

### 5. 소스 라벨링 업데이트 (`src/utils/scoring.py`)

#### A. `source_label` 함수에 새 소스 매핑 추가
```python
def source_label(source: str) -> str:
    mapping = {
        # 기존 매핑들...
        "indeed_new_country": "Indeed New Country",
        "linkedin_new_country": "LinkedIn New Country",
    }
    return mapping.get(source, source)
```

## 실제 예시: 조지아 추가 사례

### 1. 위치 용어 추가
```python
# config.py
FOCUS_LOCATION_TERMS = [
    # ... 기존 항목
    "georgia", "tbilisi", "batumi", "조지아",
]

REMOTE_GCC_LOCATION_TERMS = [
    # ... 기존 항목  
    "georgia", "tbilisi", "batumi",
]
```

### 2. 검색 URL 추가
```python
# config.py
INDEED_SEARCH_URLS = [
    # ... 기존 URL
    "https://ge.indeed.com/jobs?q=crypto+OR+web3+OR+blockchain+OR+igaming+OR+casino+OR+payment&l=georgia&sort=date",
    "https://ge.indeed.com/jobs?q=product+manager+OR+product+owner+OR+business+development+OR+sales&l=tbilisi&sort=date",
]

LINKEDIN_SEARCH_URLS = [
    # ... 기존 URL
    "https://www.linkedin.com/jobs/search/?keywords=crypto%20OR%20web3%20OR%20blockchain%20OR%20igaming%20OR%20casino%20OR%20payment&location=Georgia",
    "https://www.linkedin.com/jobs/search/?keywords=product%20manager%20OR%20product%20owner%20OR%20business%20development%20OR%20sales&location=Tbilisi%2C%20Georgia",
    "https://www.linkedin.com/jobs/search/?keywords=backend%20OR%20engineer%20OR%20developer%20OR%20software&location=Georgia",
]
```

### 3. 스코어링 로직 업데이트
```python
# scoring.py - evaluate_fit 함수
if "georgia" in text_blob or "tbilisi" in text_blob or "batumi" in text_blob or "조지아" in text_blob:
    score += 20
```

### 4. 크롤러 업데이트
```python
# scrapers.py - fetch_indeed_jobs_via_browser 함수
source_name = "indeed_uae"
if "ge.indeed.com" in search_url or "georgia" in search_url.lower():
    source_name = "indeed_georgia"

# scrapers.py - fetch_linkedin_jobs_via_browser 함수  
source_name = "linkedin_public"
if "georgia" in search_url.lower() or "tbilisi" in search_url.lower():
    source_name = "linkedin_georgia"
```

### 5. 소스 라벨링 업데이트
```python
# scoring.py - source_label 함수
mapping = {
    # ... 기존 매핑
    "indeed_georgia": "Indeed Georgia",
    "linkedin_georgia": "LinkedIn Georgia",
}
```

## 테스트 방법

### 1. 구문 검사
```bash
cd /Users/lewis/Desktop/agent
python3 -c "from src.utils.config import FOCUS_LOCATION_TERMS, INDEED_SEARCH_URLS; print('새 국가 위치 용어:', [term for term in FOCUS_LOCATION_TERMS if 'new_country' in term.lower()])"
```

### 2. 스크래퍼 실행 테스트
```bash
cd /Users/lewis/Desktop/agent
python3 src/watch/scraper.py collect 2>&1 | head -30
```

### 3. 특정 소스만 테스트
```bash
# 환경 변수로 특정 소스만 테스트
cd /Users/lewis/Desktop/agent
JOB_WATCH_SOURCES="indeed_new_country,linkedin_new_country" python3 src/watch/scraper.py collect
```

## 주의사항

### 1. Indeed 국가 도메인 확인
- Indeed는 국가별 하위 도메인을 사용합니다 (ae.indeed.com, ge.indeed.com 등)
- 새 국가의 Indeed 도메인이 존재하는지 확인하세요

### 2. LinkedIn 위치 형식
- LinkedIn은 "Country Name" 또는 "City, Country Name" 형식을 사용합니다
- 공백과 특수문자는 URL 인코딩 필요

### 3. 점수 조정
- 새 국가의 점수는 UAE와 비교하여 적절히 조정하세요
- UAE (32점) > 조지아 (20점) > 원격 GCC (16점)

### 4. Jobrapido 제한사항
- Jobrapido는 모든 국가에서 작동하지 않을 수 있습니다
- 도메인 접근 테스트 후 추가하세요

### 5. 언어 필터링
- 새 국가의 주요 언어를 `EXCLUDED_LANGUAGE_TERMS`에 추가 고려
- 한국어 지원이 필요한지 확인

## 문제 해결

### 1. URL 접근 오류
```
Network error: <urlopen error [Errno 8] nodename nor servname provided, or not known>
```
- 도메인이 존재하지 않거나 접근 불가
- curl로 도메인 접근 테스트

### 2. 검색 결과 없음
- 검색 키워드가 너무 구체적일 수 있음
- LinkedIn/Indeed에서 직접 검색 테스트

### 3. 위치 인식 실패
- 위치 용어 철자 확인
- 대소문자 구분 확인

## 기여 가이드

1. 이 문서를 참고하여 새 국가 추가
2. 변경사항 테스트
3. `docs/CHANGELOG.md`에 기록 (있는 경우)
4. 풀 리퀘스트 또는 변경사항 커밋

## 관련 문서

- [CONFIGURATION.md](./CONFIGURATION.md) - 설정 파일 설명
- [SCRAPING_SOURCES.md](./SCRAPING_SOURCES.md) - 스크래핑 소스 목록
- [SCORING_SYSTEM.md](./SCORING_SYSTEM.md) - 스코어링 시스템 설명