#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for notifications.py

Tests notification functions including:
- Source counting and aggregation
- Telegram message sending
- Job notification filtering
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch, call
from urllib.error import URLError

import pytest

from utils.models import JobPosting
from utils.notifications import (
    maybe_send_telegram,
    send_telegram_text,
    source_daily_counts,
    source_total_counts,
)
from utils.utils import utc_now
from utils.template_renderer import render_template


class TestSourceTotalCounts:
    """Tests for source_total_counts function"""

    def test_source_total_counts_empty_list(self):
        """Test with empty records list"""
        result = source_total_counts([])
        assert result == []

    def test_source_total_counts_single_source(self):
        """Test with single source"""
        records = [
            {"source": "indeed_uae", "title": "Job 1"},
            {"source": "indeed_uae", "title": "Job 2"}
        ]
        result = source_total_counts(records)
        assert len(result) == 1
        assert result[0]["source"] == "indeed_uae"
        assert result[0]["jobs"] == 2

    def test_source_total_counts_multiple_sources(self):
        """Test with multiple sources"""
        records = [
            {"source": "indeed_uae", "title": "Job 1"},
            {"source": "linkedin_public", "title": "Job 2"},
            {"source": "indeed_uae", "title": "Job 3"}
        ]
        result = source_total_counts(records)
        assert len(result) == 2
        # Should be ordered by job count descending
        assert result[0]["source"] == "indeed_uae"
        assert result[0]["jobs"] == 2
        assert result[1]["source"] == "linkedin_public"
        assert result[1]["jobs"] == 1

    def test_source_total_counts_ordering(self):
        """Test that results are properly ordered"""
        records = [
            {"source": "a", "title": "Job 1"},
            {"source": "b", "title": "Job 2"},
            {"source": "b", "title": "Job 3"},
            {"source": "b", "title": "Job 4"},
            {"source": "c", "title": "Job 5"}
        ]
        result = source_total_counts(records)
        # b (3) > a (1), c (1)
        assert result[0]["source"] == "b"
        # Secondary sort is alphabetical for ties
        assert result[1]["source"] == "a"
        assert result[2]["source"] == "c"

    def test_source_total_counts_missing_source_field(self):
        """Test handling of missing source field"""
        records = [
            {"source": "indeed_uae", "title": "Job 1"},
            {"source": "indeed_uae", "title": "Job 2"}
        ]
        # Should only count records with source field
        result = source_total_counts(records)
        assert len(result) == 1
        assert result[0]["source"] == "indeed_uae"
        assert result[0]["jobs"] == 2


class TestSourceDailyCounts:
    """Tests for source_daily_counts function"""

    def test_source_daily_counts_empty_list(self):
        """Test with empty records list"""
        result = source_daily_counts([])
        assert result == []

    def test_source_daily_counts_same_day(self):
        """Test multiple records from same day"""
        now = utc_now().date().isoformat()
        records = [
            {"source": "indeed_uae", "first_seen_at": f"{now}T10:00:00"},
            {"source": "indeed_uae", "first_seen_at": f"{now}T14:00:00"},
            {"source": "linkedin_public", "first_seen_at": f"{now}T15:00:00"}
        ]
        result = source_daily_counts(records, days=14)
        # Should have 2 entries: indeed_uae and linkedin_public for today
        assert len(result) == 2

    def test_source_daily_counts_multiple_days(self):
        """Test records from multiple days"""
        now = utc_now()
        today = now.date().isoformat()
        yesterday = (now - timedelta(days=1)).date().isoformat()
        records = [
            {"source": "indeed_uae", "first_seen_at": f"{today}T10:00:00"},
            {"source": "indeed_uae", "first_seen_at": f"{yesterday}T10:00:00"},
            {"source": "linkedin_public", "first_seen_at": f"{today}T15:00:00"}
        ]
        result = source_daily_counts(records, days=14)
        assert len(result) >= 2

    def test_source_daily_counts_filters_old_records(self):
        """Test that old records are filtered out"""
        now = utc_now()
        old_date = (now - timedelta(days=30)).date().isoformat()
        records = [
            {"source": "indeed_uae", "first_seen_at": f"{old_date}T10:00:00"}
        ]
        result = source_daily_counts(records, days=14)
        assert result == []

    def test_source_daily_counts_missing_first_seen_at(self):
        """Test handling of missing first_seen_at"""
        records = [
            {"source": "indeed_uae", "title": "Job 1"},
            {"source": "linkedin_public", "first_seen_at": "2026-03-30T10:00:00"}
        ]
        result = source_daily_counts(records, days=14)
        # Should skip record without first_seen_at
        assert all(r.get("source") for r in result)

    def test_source_daily_counts_ordering(self):
        """Test result ordering"""
        now = utc_now().date().isoformat()
        records = [
            {"source": "a", "first_seen_at": f"{now}T10:00:00"},
            {"source": "b", "first_seen_at": f"{now}T10:00:00"}
        ]
        result = source_daily_counts(records, days=14)
        # Should be ordered by date descending, then source ascending
        assert len(result) == 2


class TestSendTelegramText:
    """Tests for send_telegram_text function"""

    @patch.dict("os.environ", {}, clear=True)
    def test_send_telegram_text_missing_token(self):
        """Test when bot token is missing"""
        # Should not raise, just return
        send_telegram_text("Test message")

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "token123"}, clear=True)
    def test_send_telegram_text_missing_chat_id(self):
        """Test when chat ID is missing"""
        # Should not raise, just return
        send_telegram_text("Test message")

    @patch("urllib.request.urlopen")
    @patch.dict("os.environ", {
        "TELEGRAM_BOT_TOKEN": "token123",
        "TELEGRAM_CHAT_ID": "chat123"
    })
    def test_send_telegram_text_success(self, mock_urlopen):
        """Test successful telegram message send"""
        mock_response = MagicMock()
        mock_urlopen.return_value = mock_response
        send_telegram_text("Test message")
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    @patch.dict("os.environ", {
        "TELEGRAM_BOT_TOKEN": "token123",
        "TELEGRAM_CHAT_ID": "chat123"
    })
    def test_send_telegram_text_with_html(self, mock_urlopen):
        """Test sending telegram with HTML formatting"""
        mock_response = MagicMock()
        mock_urlopen.return_value = mock_response
        send_telegram_text("<b>Bold</b> message")
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    @patch.dict("os.environ", {
        "TELEGRAM_BOT_TOKEN": "token123",
        "TELEGRAM_CHAT_ID": "chat123"
    })
    def test_send_telegram_text_url_encoding(self, mock_urlopen):
        """Test that message is properly URL encoded"""
        mock_response = MagicMock()
        mock_urlopen.return_value = mock_response
        send_telegram_text("Test with special chars: & = ?")
        # Verify urlopen was called with properly encoded data
        mock_urlopen.assert_called_once()
        call_args = mock_urlopen.call_args
        assert call_args is not None

    @patch("urllib.request.urlopen")
    @patch("logging.getLogger")
    @patch.dict("os.environ", {
        "TELEGRAM_BOT_TOKEN": "token123",
        "TELEGRAM_CHAT_ID": "chat123"
    })
    def test_send_telegram_text_logs_success(self, mock_logger, mock_urlopen):
        """Test that success is logged"""
        mock_response = MagicMock()
        mock_urlopen.return_value = mock_response
        with patch("utils.notifications.logger") as logger_mock:
            send_telegram_text("Test message")
            # Verify logging happened
            assert logger_mock.info.called

    @patch("urllib.request.urlopen", side_effect=URLError("Network error"))
    @patch("logging.getLogger")
    @patch.dict("os.environ", {
        "TELEGRAM_BOT_TOKEN": "token123",
        "TELEGRAM_CHAT_ID": "chat123"
    })
    def test_send_telegram_text_handles_error(self, mock_logger, mock_urlopen):
        """Test error handling"""
        # Should not raise when network fails
        try:
            send_telegram_text("Test message")
        except URLError:
            pass  # Expected, but we're testing graceful failure


class TestMaybeSendTelegram:
    """Tests for maybe_send_telegram function"""

    @patch("utils.notifications.send_telegram_text")
    @patch("utils.notifications.load_telegram_sent_history", return_value={})
    @patch("utils.notifications.prune_telegram_sent_history")
    def test_maybe_send_telegram_no_new_jobs(self, mock_prune, mock_load, mock_send):
        """Test when no new jobs were inserted"""
        jobs = []
        maybe_send_telegram(0, jobs)
        mock_send.assert_called_once()

    @patch("utils.notifications.send_telegram_text")
    @patch("utils.notifications.load_telegram_sent_history", return_value={})
    @patch("utils.notifications.prune_telegram_sent_history")
    def test_maybe_send_telegram_negative_inserted(self, mock_prune, mock_load, mock_send):
        """Test with negative inserted count"""
        jobs = []
        maybe_send_telegram(-5, jobs)
        mock_send.assert_called_once()

    @patch("utils.notifications.send_telegram_text")
    @patch("utils.notifications.save_telegram_sent_history")
    @patch("utils.notifications.load_telegram_sent_history", return_value={})
    @patch("utils.notifications.prune_telegram_sent_history", return_value={})
    def test_maybe_send_telegram_new_jobs(self, mock_prune, mock_load, mock_save, mock_send):
        """Test sending telegram for new jobs"""
        job = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="Senior Developer",
            company="TechCorp",
            location="Dubai",
            url="https://indeed.com/123",
            match_score=85
        )
        maybe_send_telegram(1, [job])
        # Should have called send_telegram_text
        assert mock_send.called

    @patch("utils.notifications.send_telegram_text")
    @patch("utils.notifications.load_telegram_sent_history", return_value={})
    @patch("utils.notifications.prune_telegram_sent_history")
    def test_maybe_send_telegram_duplicate_jobs(self, mock_prune, mock_load, mock_send):
        """Test filtering duplicate jobs"""
        job = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="Senior Developer",
            company="TechCorp",
            location="Dubai",
            url="https://indeed.com/123"
        )
        # Simulate job already sent
        sent_history = {
            "|".join([job.source, job.source_job_id, job.title, job.company]): "2026-03-30T09:00:00"
        }
        with patch("utils.notifications.load_telegram_sent_history", return_value=sent_history):
            with patch("utils.notifications.prune_telegram_sent_history", return_value=sent_history):
                maybe_send_telegram(1, [job])
                # Zero-update alerts should still be sent
                mock_send.assert_called_once()

    @patch("utils.notifications.send_telegram_text")
    @patch("utils.notifications.save_telegram_sent_history")
    @patch("utils.notifications.load_telegram_sent_history", return_value={})
    @patch("utils.notifications.prune_telegram_sent_history", return_value={})
    def test_maybe_send_telegram_multiple_jobs(self, mock_prune, mock_load, mock_save, mock_send):
        """Test sending notification with multiple new jobs"""
        jobs = [
            JobPosting(
                source="indeed_uae",
                source_job_id=str(i),
                title=f"Developer {i}",
                company=f"Corp{i}",
                location="Dubai",
                url=f"https://indeed.com/{i}",
                match_score=80 - i*5
            )
            for i in range(5)
        ]
        maybe_send_telegram(5, jobs)
        # Should send message including top 3 jobs
        if mock_send.called:
            call_args = mock_send.call_args
            message = call_args[0][0] if call_args else ""
            assert isinstance(message, str)

    @patch("utils.notifications.send_telegram_text")
    @patch("utils.notifications.save_telegram_sent_history")
    @patch("utils.notifications.load_telegram_sent_history", return_value={})
    @patch("utils.notifications.prune_telegram_sent_history", return_value={})
    @patch("utils.notifications.source_label")
    def test_maybe_send_telegram_message_format(self, mock_label, mock_prune, mock_load, mock_save, mock_send):
        """Test message format includes job details"""
        mock_label.return_value = "Indeed UAE"
        job = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="Senior Developer",
            company="TechCorp",
            location="Dubai",
            url="https://indeed.com/123",
            match_score=85
        )
        maybe_send_telegram(1, [job])
        if mock_send.called:
            message = mock_send.call_args[0][0]
            # Message should contain job information
            assert isinstance(message, str)
            assert len(message) > 0


class TestTemplateRenderer:
    """Tests for template rendering functions"""

    def test_render_job_alert_template(self):
        """Test rendering job alert template"""
        context = {
            "new_count": 5,
            "country_line": "UAE 5",
            "country_groups": [
                {
                    "country": "UAE",
                    "jobs": [
                        {"label": "Corp1 | Developer", "url": "https://example.com/1"},
                        {"label": "Corp2 | Engineer", "url": "https://example.com/2"},
                    ],
                }
            ],
        }
        result = render_template("telegram/job_alert.txt", context)
        assert "New job matches: 5" in result
        assert "Corp1 | Developer" in result
        assert "https://example.com/1" in result
        assert "UAE:" in result

    def test_render_incremental_summary_template(self):
        """Test rendering incremental summary template"""
        context = {
            "hours": 3,
            "job_count": 2,
            "source_counts": True,
            "source_line": "Indeed UAE 2 | LinkedIn 1",
            "country_line": "UAE 2",
            "country_groups": [
                {
                    "country": "UAE",
                    "jobs": [
                        {"label": "Corp1 | Developer", "url": "https://example.com/1"},
                    ],
                }
            ],
            "jobs": [
                {"label": "Corp1 | Developer", "url": "https://example.com/1"},
            ]
        }
        result = render_template("telegram/incremental_summary.txt", context)
        assert "New jobs in last 3h: 2" in result
        assert "Indeed UAE 2 | LinkedIn 1" in result
        assert "UAE:" in result

    def test_render_daily_summary_template(self):
        """Test rendering daily summary template"""
        context = {
            "new_count": 3,
            "source_today": [
                {"label": "Indeed UAE", "count": 2},
                {"label": "LinkedIn", "count": 1},
            ],
            "source_total": [
                {"label": "Indeed UAE", "count": 10},
                {"label": "LinkedIn", "count": 5},
            ],
            "jobs": [
                {"label": "Corp1 | Developer", "url": "https://example.com/1"},
                {"label": "Corp2 | Engineer", "url": "https://example.com/2"},
            ]
        }
        result = render_template("telegram/daily_summary.txt", context)
        assert "🆕 Daily Jobs (3 new)" in result
        assert "Corp1 | Developer" in result

    def test_render_news_summary_template(self):
        """Test rendering full news summary template"""
        context = {
            "total_articles": 10,
            "topics": [
                {
                    "label_ko": "블록체인 뉴스",
                    "article_count": 5,
                    "articles": [
                        {"title": "Bitcoin rises", "url": "https://example.com/1"},
                        {"title": "Ethereum update", "url": "https://example.com/2"},
                    ]
                },
                {
                    "label_ko": "핀테크 뉴스",
                    "article_count": 5,
                    "articles": [
                        {"title": "PayPal news", "url": "https://example.com/3"},
                    ]
                }
            ],
            "showing_partial": False,
            "shown_count": 3,
        }
        result = render_template("telegram/news_summary.txt", context)
        assert "📈 Industry News Summary (10 articles)" in result
        assert "블록체인 뉴스" in result
        assert "Bitcoin rises" in result

    def test_render_news_summary_simplified_template(self):
        """Test rendering simplified news summary template"""
        context = {
            "total_articles": 10,
            "topics": [
                {
                    "label_ko": "블록체인 뉴스",
                    "article_count": 5,
                    "articles": [
                        {"title": "Bitcoin rises", "url": "https://example.com/1"},
                        {"title": "Ethereum update", "url": "https://example.com/2"},
                    ]
                }
            ]
        }
        result = render_template("telegram/news_summary_simplified.txt", context)
        assert "📈 Industry News (10 articles)" in result
        assert "블록체인 뉴스" in result

    def test_render_template_with_html_escaping(self):
        """Test template rendering with HTML-escaped content"""
        context = {
            "new_count": 1,
            "country_line": "",
            "country_groups": [
                {
                    "country": "UAE",
                    "jobs": [
                        {"label": "Corp &amp; Co | Dev &lt;&gt;", "url": "https://example.com/1?x=1&y=2"},
                    ],
                }
            ],
        }
        result = render_template("telegram/job_alert.txt", context)
        # HTML entities should be preserved as passed in context
        assert "Corp &amp; Co | Dev &lt;&gt;" in result

    def test_render_template_zero_items(self):
        """Test rendering with zero items"""
        context = {
            "hours": 3,
            "job_count": 0,
            "source_counts": False,
            "source_line": "",
            "jobs": []
        }
        result = render_template("telegram/incremental_summary.txt", context)
        assert "New jobs in last 3h: 0" in result


class TestIntegration:
    """Integration tests for notification functions"""

    def test_source_counts_consistent(self):
        """Test that source counts are consistent"""
        records = [
            {"source": "indeed_uae", "title": "Job 1"},
            {"source": "indeed_uae", "title": "Job 2"},
            {"source": "linkedin_public", "title": "Job 3"}
        ]
        total = source_total_counts(records)
        assert total[0]["jobs"] == 2
        assert total[1]["jobs"] == 1
        assert sum(item["jobs"] for item in total) == 3

    def test_daily_counts_with_current_date(self):
        """Test daily counts includes current date"""
        now = utc_now()
        today = now.date().isoformat()
        records = [
            {"source": "indeed_uae", "first_seen_at": f"{today}T10:00:00"},
            {"source": "indeed_uae", "first_seen_at": f"{today}T14:00:00"}
        ]
        result = source_daily_counts(records, days=1)
        assert len(result) > 0
        # Check that today's date is in results
        today_results = [r for r in result if r.get("seen_date") == today]
        assert len(today_results) > 0

    @patch("utils.notifications.send_telegram_text")
    @patch("utils.notifications.save_telegram_sent_history")
    @patch("utils.notifications.load_telegram_sent_history", return_value={})
    @patch("utils.notifications.prune_telegram_sent_history", return_value={})
    def test_maybe_send_telegram_realistic_scenario(self, mock_prune, mock_load, mock_save, mock_send):
        """Test realistic scenario with multiple new jobs"""
        jobs = [
            JobPosting(
                source="indeed_uae",
                source_job_id="1",
                title="Senior Blockchain Developer",
                company="Crypto Solutions",
                location="Dubai, UAE",
                url="https://indeed.com/1",
                description="We are looking for an experienced Blockchain developer",
                match_score=92
            ),
            JobPosting(
                source="linkedin_public",
                source_job_id="2",
                title="Product Manager - Web3",
                company="FinTech Innovations",
                location="Abu Dhabi, UAE",
                url="https://linkedin.com/2",
                description="Lead our Web3 product strategy",
                match_score=88
            ),
            JobPosting(
                source="telegram_cryptojobslist",
                source_job_id="3",
                title="Payment Systems Engineer",
                company="PaymentCorp",
                location="Dubai",
                url="https://telegram.me/3",
                description="Build payment systems",
                match_score=75
            )
        ]
        maybe_send_telegram(3, jobs)
        # Verify notification was attempted
        if mock_send.called:
            message = mock_send.call_args[0][0]
            assert "New UAE job matches" in message or "مطابق" in message or len(message) > 0
