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
    @patch('utils.notifications.load_telegram_sent_history')
    @patch('utils.notifications.load_resume_text')
    def test_no_new_jobs_no_message(self, mock_resume, mock_history, mock_send):
        """새 공고가 없어도 0건 요약 메시지를 보냄"""
        mock_resume.return_value = "cloud engineer"
        mock_history.return_value = {}

        # 빈 DB (새 공고 없음)
        db = MagicMock()
        db.jobs_first_seen_since.return_value = []
        db.fetch_all_jobs.return_value = []

        send_daily_summary(db)

        # 0건 요약 메시지를 보냄
        mock_send.assert_called_once()

    @patch('utils.notifications.send_telegram_text')
    @patch('utils.notifications.save_telegram_sent_history')
    @patch('utils.notifications.load_telegram_sent_history')
    @patch('utils.notifications.focus_records')
    @patch('utils.notifications.load_resume_text')
    def test_with_new_jobs_sends_message(self, mock_resume, mock_focus, mock_history, mock_save, mock_send):
        """새 공고가 있으면 메시지를 보냄"""
        mock_resume.return_value = "cloud engineer"
        mock_history.return_value = {}

        # 새 공고가 있음 (focus_records가 필터링한 후)
        new_job = {
            'source': 'indeed_uae',
            'source_job_id': '123',
            'title': 'Cloud Engineer',
            'company': 'ABC Corp',
            'location': 'Dubai',
            'url': 'http://example.com/job/123',
            'qualifies': True
        }

        # focus_records가 적어도 하나의 공고를 반환
        mock_focus.side_effect = [[new_job], [new_job]]

        db = MagicMock()
        db.jobs_first_seen_since.return_value = [new_job]
        db.fetch_all_jobs.return_value = [new_job]

        send_daily_summary(db)

        # 메시지를 보냄
        mock_send.assert_called_once()


class TestSendNewsSummary:
    """send_news_summary 테스트"""

    @patch('utils.notifications.send_telegram_text')
    @patch('utils.notifications.load_telegram_sent_history')
    def test_no_news_no_message(self, mock_history, mock_send):
        """뉴스가 없으면 메시지를 보내지 않음"""
        mock_history.return_value = {}

        # 뉴스 없음
        send_news_summary([])

        mock_send.assert_not_called()

    @patch('utils.notifications.send_telegram_text')
    @patch('utils.notifications.save_telegram_sent_history')
    @patch('utils.notifications.load_telegram_sent_history')
    def test_with_unsent_news_sends_message(self, mock_history, mock_save, mock_send):
        """미발송 뉴스가 있으면 메시지를 보냄"""
        mock_history.return_value = {}  # 아직 보낸 뉴스 없음

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
    @patch('utils.notifications.load_telegram_sent_history')
    def test_all_news_already_sent_no_message(self, mock_history, mock_send):
        """모든 뉴스가 이미 발송됨 → 메시지 안 보냄"""
        news = NewsItem(
            source='rss_igaming_business',
            title='Old News',
            url='http://example.com/news/old',
            published_at=(utc_now() - timedelta(days=1)).isoformat(),
            summary='Summary'
        )

        # 이미 발송한 뉴스 이력
        mock_history.return_value = {
            'http://example.com/news/old': utc_now().isoformat()
        }

        send_news_summary([news])

        # 메시지를 보내지 않음
        mock_send.assert_not_called()
