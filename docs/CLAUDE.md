# CLAUDE.md

## 프로젝트 개요

UAE/GCC 지역 crypto/fintech/igaming job scraping and news system

## 핵심 구조

src/
  core/
  services/
  utils/

## 주요 명령어

scraper 실행:
python3 src/core/scraper.py daily

dashboard:
python3 src/services/serve_dashboard.py

## 개발 원칙

- stdlib 우선
- sqlite 사용
- 중복 제거 SHA1

## 중요한 파일

scrapers.py - scraping
scoring.py - scoring
db.py - database
notifications.py - telegram

## 작업 지침

- 작은 변경 우선
- 테스트 먼저 실행
- 기존 구조 유지