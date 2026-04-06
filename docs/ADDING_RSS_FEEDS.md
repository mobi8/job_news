# RSS 피드 추가 가이드

이 문서는 UAE Job Watcher 시스템에 새로운 RSS 피드를 추가하는 방법을 설명합니다.

## 개요

시스템은 다음과 같은 구성 요소로 RSS 피드를 처리합니다:
1. **RSS 피드 정의** (`config.py` - `NEWS_RSS_FEEDS`)
2. **대시보드 소스 라벨링** (`scraper.py` - 소스 정보)
3. **대시보드 소스 표시** (`serve_dashboard.py` - API 엔드포인트 및 뷰)

## 단계별 추가 가이드

### 1. RSS 피드 추가 (`src/utils/config.py`)

#### A. `NEWS_RSS_FEEDS` 배열에 새 항목 추가
```python
NEWS_RSS_FEEDS = [
    # 기존 피드들...
    
    # 새 RSS 피드 추가
    {
        "url": "https://example.com/rss/feed.xml",
        "source": "rss_example_source",      # 소스 식별자 (고유해야 함)
        "label": "Example News Feed",        # 사람이 읽을 수 있는 라벨
    },
]
```

#### 파라미터 설명:
- `url`: RSS 피드 URL (RSS 2.0 또는 Atom 형식 지원)
- `source`: 내부 소스 식별자 (접두사 `rss_` 권장)
- `label`: 대시보드에 표시될 이름

### 2. 소스 정보 추가 (`src/core/scraper.py`)

#### A. `source_info` 딕셔너리에 새 소스 정보 추가
```python
source_info = {
    # 기존 소스 정보...
    
    "rss_example_source": {
        "label": "Example News Feed",      # 소스 라벨
        "emoji": "🎯",                     # 이모지 (선택사항)
        "description": "예제 뉴스 피드 설명", # 설명
        "color": "#FF6B6B"                 # 색상 코드 (HEX)
    }
}
```

#### B. 색상 팔레트 추천:
- iGaming 관련: `#FF6B6B`, `#FFD166`, `#F78C6B` (따뜻한 색상)
- Fintech 관련: `#4ECDC4`, `#118AB2`, `#073B4C` (차가운 색상)
- Crypto 관련: `#06D6A0`, `#7209B7`, `#EF476F` (강렬한 색상)

### 3. 대시보드 업데이트 (`src/services/serve_dashboard.py`)

#### A. `/api/health` 엔드포인트에 새 소스 추가
```python
"news_sources": [
    # 기존 소스들...
    
    {"source": "rss_example_source", "label": "🎯 Example Feed", "url": "https://example.com/rss/feed.xml"}
]
```

#### B. `_get_news_section_injection` 함수의 소스 매핑 업데이트
```python
const sourceMap = {
    // 기존 매핑...
    
    'rss_example_source': '🎯 Example Feed'
};
```

### 4. 테스트 및 검증

#### A. RSS 피드 접근성 테스트
```bash
# curl로 RSS 피드 접근 테스트
curl -s -I "https://example.com/rss/feed.xml"

# Python으로 RSS 파싱 테스트
python3 -c "
import urllib.request
import xml.etree.ElementTree as ET

url = 'https://example.com/rss/feed.xml'
try:
    response = urllib.request.urlopen(url)
    xml_data = response.read()
    root = ET.fromstring(xml_data)
    print('RSS 피드 접근 성공:', root.tag)
except Exception as e:
    print('RSS 피드 접근 실패:', e)
"
```

#### B. 시스템 테스트 실행
```bash
cd /Users/lewis/Desktop/agent

# 스크래퍼 실행 (뉴스 수집 테스트)
python3 src/core/scraper.py collect 2>&1 | grep -A5 -B5 "Fetching RSS feed"

# 대시보드 시작
python3 src/services/serve_dashboard.py &
sleep 3

# API 테스트
curl -s "http://127.0.0.1:8765/api/health" | python3 -m json.tool | grep -A10 "news_sources"
```

## 실제 예시: InterGame RSS 피드 추가

### 1. `config.py`에 추가
```python
NEWS_RSS_FEEDS = [
    # 기존 피드들...
    
    {
        "url": "https://www.intergameonline.com/rss/igaming/news",
        "source": "rss_intergame_news",
        "label": "InterGame iGaming News",
    },
    {
        "url": "https://www.intergameonline.com/rss/igaming/cryptocurrency",
        "source": "rss_intergame_crypto",
        "label": "InterGame Cryptocurrency",
    },
]
```

### 2. `scraper.py`에 소스 정보 추가
```python
source_info = {
    # 기존 소스 정보...
    
    "rss_intergame_news": {
        "label": "InterGame News",
        "emoji": "🎲",
        "description": "InterGame iGaming 뉴스 및 업계 소식",
        "color": "#FFD166"
    },
    "rss_intergame_crypto": {
        "label": "InterGame Crypto",
        "emoji": "₿",
        "description": "InterGame 암호화폐 및 블록체인 관련 뉴스",
        "color": "#F78C6B"
    },
}
```

### 3. `serve_dashboard.py` 업데이트
```python
# /api/health 엔드포인트
"news_sources": [
    # 기존 소스들...
    {"source": "rss_intergame_news", "label": "🎲 InterGame News", "url": "https://www.intergameonline.com/rss/igaming/news"},
    {"source": "rss_intergame_crypto", "label": "₿ InterGame Crypto", "url": "https://www.intergameonline.com/rss/igaming/cryptocurrency"}
]

# 소스 매핑
const sourceMap = {
    # 기존 매핑...
    'rss_intergame_news': '🎲 InterGame News',
    'rss_intergame_crypto': '₿ InterGame Crypto'
};
```

## 주의사항

### 1. RSS 형식 지원
- **RSS 2.0**: `<rss><channel><item>` 구조
- **Atom**: `<feed><entry>` 구조
- 두 형식 모두 `fetch_rss_news` 함수에서 지원

### 2. 접근성 문제
```
Network error: <urlopen error [Errno 8] nodename nor servname provided, or not known>
```
- URL이 존재하지 않거나 DNS 문제
- 방화벽 또는 접근 제한

### 3. 파싱 오류
```
Failed to parse RSS XML from [URL]: [Error]
```
- XML 형식이 잘못됨
- 인코딩 문제 (UTF-8 강제)

### 4. 성능 고려사항
- 너무 많은 RSS 피드는 성능 저하 유발
- 각 피드 타임아웃: 20초
- 최대 동시 요청 수: 제한 없음 (순차 처리)

## 문제 해결

### 1. RSS 피드 접근 실패
```python
# 디버깅 스크립트
import urllib.request
import ssl

url = "https://example.com/rss/feed.xml"
context = ssl._create_unverified_context()  # SSL 검증 우회 (테스트용)

try:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    with urllib.request.urlopen(req, context=context, timeout=30) as response:
        print(f"Status: {response.status}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")
        print(f"First 500 chars:\n{response.read(500)}")
except Exception as e:
    print(f"Error: {e}")
```

### 2. XML 파싱 오류
```python
# XML 구조 분석
import xml.etree.ElementTree as ET

# 피드 다운로드 후...
root = ET.fromstring(xml_data)
print("Root tag:", root.tag)
print("Root attributes:", root.attrib)

# 네임스페이스 확인
print("Namespaces:", {k: v for k, v in root.attrib.items() if 'xmlns' in k})

# 아이템 찾기
items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
print(f"Found {len(items)} items")
```

### 3. 대시보드 표시 문제
- 브라우저 개발자 도구(F12) 콘솔 확인
- 네트워크 탭에서 API 응답 확인
- `/api/health` 엔드포인트 직접 접속 테스트

## 모범 사례

### 1. 소스 식별자 명명 규칙
- 접두사: `rss_`
- 형식: `rss_[provider]_[category]`
- 예: `rss_intergame_news`, `rss_finextra_payments`

### 2. 이모지 사용 가이드
- iGaming: 🎮, 🎲, 🎰, 🃏
- Fintech: 💰, 💳, 🏦, 📈
- Crypto: ₿, 🔗, ⛓️, 🪙
- 일반: 📰, 🗞️, 📊, 🔍

### 3. 색상 코딩
- 같은 제공자의 다른 카테고리는 유사 색상 사용
- 색상 대비 고려 (가독성)
- 웹 접근성 고려 (색맹 사용자)

## 관련 문서

- [ADDING_NEW_COUNTRY.md](./ADDING_NEW_COUNTRY.md) - 새 국가 추가 가이드
- [CONFIGURATION.md](./CONFIGURATION.md) - 설정 파일 설명
- [DASHBOARD_MODIFICATIONS.md](./DASHBOARD_MODIFICATIONS.md) - 대시보드 수정 가이드

## RSS 피드 추천 소스

### iGaming 업계
- iGaming Business
- InterGame Online
- Gambling Insider
- Casino.org News

### Fintech & Payments
- Fintech News UAE
- FinExtra
- The Paypers
- PaymentSource

### Crypto & Web3
- CoinDesk RSS
- Cointelegraph
- The Block
- Decrypt

### 지역별 뉴스
- GCC Fintech (UAE, Saudi, Qatar)
- Asian iGaming (Philippines, Cambodia)
- European Gaming (Malta, Gibraltar)