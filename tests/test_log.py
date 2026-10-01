"""Tests for structlog-config logging setup."""

from __future__ import annotations

import os

from amazon_lunchmoney.log import log, setup_logging


def test_setup_logging_verbose(monkeypatch) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    setup_logging(verbose=True)
    assert os.environ.get("LOG_LEVEL") == "DEBUG"


def test_setup_logging_log_path(monkeypatch, tmp_path) -> None:
    test_path = str(tmp_path / "test.log")
    monkeypatch.setenv("AMAZON_LUNCHMONEY_LOG_PATH", test_path)
    monkeypatch.delenv("PYTHON_LOG_PATH", raising=False)
    setup_logging()
    assert os.environ.get("PYTHON_LOG_PATH") == test_path


def test_log_methods() -> None:
    log.info("test log info message", key="val")
    log.debug("test log debug message", num=123)
