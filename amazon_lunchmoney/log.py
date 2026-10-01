"""Logging configuration using structlog-config."""

from __future__ import annotations

import logging
import os
import sys

import structlog
from structlog_config import LoggerWithContext, configure_logger


def setup_logging(verbose: bool = False) -> LoggerWithContext:
    # Map AMAZON_LUNCHMONEY_LOG_PATH to PYTHON_LOG_PATH for structlog-config
    if log_path := os.environ.get("AMAZON_LUNCHMONEY_LOG_PATH"):
        os.environ["PYTHON_LOG_PATH"] = log_path

    if verbose:
        os.environ["LOG_LEVEL"] = "DEBUG"

    # Suppress verbose INFO and AFC advisory WARNING logs from google_genai
    logging.getLogger("google_genai.models").setLevel(logging.ERROR)

    return configure_logger(
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr)
    )


log = setup_logging()
