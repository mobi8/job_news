#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
디버그: send_daily_summary와 send_news_summary가 메시지를 언제 보내는지 테스트
"""

import pytest
from unittest.mock import MagicMock, patch
from utils.models import NewsItem
from utils.notifications import send_daily_summary, send_news_summary
from utils.utils import utc_now
from datetime import timedelta


class TestSendDailySummary:
    """send_daily_summary 테스트"""

    @patch('utils.notifications.send_telegram_text')
    def test_no_new_jobs_no_message(self, mock_send):
        """새 공고가 없어도 0건 요약 메시지를 보냄"""

        # 빈 DB (새 공고 없음)
        db = MagicMock()
        db.jobs_first_seen_since.return_value = []
        db.fetch_all_jobs.return_value = []

        send_daily_summary(db)

        # 0건 요약 메시지를 보냄
        mock_send.assert_called_once()

    @patch('utils.notifications.send_telegram_text')
    def test_with_new_jobs_sends_message(self, mock_send):
        """새 공고가 있으면 메시지를 보냄"""
        # 새 공고가 있음
        new_job = {
            'source': 'indeed_uae',
            'source_job_id': '123',
            'title': 'Cloud Engineer',
            'company': 'ABC Corp',
            'location': 'Dubai',
            'url': 'http://example.com/job/123',
            'match_score': 80,
        }

        db = MagicMock()
        db.jobs_first_seen_since.return_value = [new_job]
        db.fetch_all_jobs.return_value = [new_job]

        send_daily_summary(db)

        # 메시지를 보냄
        mock_send.assert_called_once()


class TestSendNewsSummary:
    """send_news_summary 테스트"""

    @patch('utils.notifications.send_telegram_text')
    def test_no_news_no_message(self, mock_send):
        """뉴스가 없으면 0건 메시지를 보냄"""

        # 뉴스 없음
        send_news_summary([])

        mock_send.assert_called_once()

    @patch('utils.notifications.send_telegram_text')
    def test_with_unsent_news_sends_message(self, mock_send):
        """뉴스가 있으면 메시지를 보냄"""

        # 새 뉴스 아이템
        news = NewsItem(
            source='rss_igaming_business',
            title='New iGaming Regulation',
            url='http://example.com/news/1',
            published_at=utc_now().isoformat(),
            summary='Summary'
        )

        send_news_summary([news])

        # 메시지를 보냄
        mock_send.assert_called_once()

    @patch('utils.notifications.send_telegram_text')
    def test_all_news_already_sent_no_message(self, mock_send):
        """같은 뉴스도 배치가 다시 시작되면 다시 보냄"""
        news = NewsItem(
            source='rss_igaming_business',
            title='Old News',
            url='http://example.com/news/old',
            published_at=(utc_now() - timedelta(days=1)).isoformat(),
            summary='Summary'
        )

        send_news_summary([news])

        # 배치 기준으로 다시 보내는 것이 정상
        mock_send.assert_called_once()
