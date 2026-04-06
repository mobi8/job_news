#!/usr/bin/env python3
"""
Centralized logging configuration for all modules.
Provides structured logging with timestamps, levels, and log rotation.
"""

import logging
import logging.handlers
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


LOGS_DIR = Path("/Users/lewis/Desktop/agent/logs")
LOGS_DIR.mkdir(exist_ok=True, parents=True)


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs JSON logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
            "line": record.lineno,
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    """Clean plain text formatter."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).isoformat()
        return f"[{timestamp}] {record.levelname:8} {record.name:20} {record.getMessage()}"


def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    json_format: bool = False,
) -> logging.Logger:
    """
    Setup a logger for a specific module.

    Args:
        name: Logger name (typically __name__)
        log_file: Log file name in logs/ directory (e.g., 'scraper.log')
        level: Logging level (default: INFO)
        json_format: Use JSON format instead of plain text

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    logger.handlers = []

    # Determine formatter
    formatter_class = JSONFormatter if json_format else PlainFormatter
    formatter = formatter_class()

    # Console handler (always INFO level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler with rotation
    if log_file:
        log_path = LOGS_DIR / log_file
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,  # Keep 5 backup files
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Module-specific loggers
scraper_logger = setup_logger("scraper", "scraper.log", json_format=True)
watch_logger = setup_logger("watch_loop", "watch_loop.log", json_format=True)
dashboard_logger = setup_logger("dashboard", "dashboard.log", json_format=True)
db_logger = setup_logger("database", "database.log", json_format=True)
notifications_logger = setup_logger("notifications", "notifications.log", json_format=True)


def get_logger(module_name: str) -> logging.Logger:
    """Get or create logger for a module."""
    return logging.getLogger(module_name)
