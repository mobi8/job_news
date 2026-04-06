#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for the job scraper project

This package contains comprehensive tests for:
- models.py - JobPosting and NewsItem dataclasses
- db.py - Database class for SQLite operations
- scoring.py - Job matching and scoring functions
- utils.py - Utility functions
- notifications.py - Telegram notification functions
- config.py - Configuration loading (optional)

Test structure:
- test_models.py - Data model tests
- test_db.py - Database operations tests
- test_scoring.py - Job matching and filtering tests
- test_utils.py - Utility function tests
- test_notifications.py - Notification and messaging tests

Running tests:
    pytest                    # Run all tests
    pytest -v                 # Verbose output
    pytest tests/test_models.py  # Run specific test file
    pytest tests/test_models.py::TestJobPosting  # Run specific test class
    pytest -k "test_fingerprint"  # Run tests matching pattern
    pytest --markers mock     # Run tests with specific marker
"""
