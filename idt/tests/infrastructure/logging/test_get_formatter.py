"""Tests for get_formatter() factory function."""

import logging
import pytest

from src.infrastructure.logging.formatters import (
    get_formatter,
    PrettyFormatter,
    StructuredFormatter,
)


class TestGetFormatter:
    """get_formatter() 환경변수 기반 포매터 선택 테스트."""

    def test_default_returns_pretty(self, monkeypatch):
        """LOG_FORMAT 미설정 시 PrettyFormatter를 반환한다."""
        monkeypatch.delenv("LOG_FORMAT", raising=False)
        formatter = get_formatter()
        assert isinstance(formatter, PrettyFormatter)

    def test_pretty_returns_pretty(self, monkeypatch):
        """LOG_FORMAT=pretty 시 PrettyFormatter를 반환한다."""
        monkeypatch.setenv("LOG_FORMAT", "pretty")
        formatter = get_formatter()
        assert isinstance(formatter, PrettyFormatter)

    def test_compact_returns_structured(self, monkeypatch):
        """LOG_FORMAT=compact 시 StructuredFormatter를 반환한다."""
        monkeypatch.setenv("LOG_FORMAT", "compact")
        formatter = get_formatter()
        assert isinstance(formatter, StructuredFormatter)

    def test_case_insensitive_compact(self, monkeypatch):
        """LOG_FORMAT=COMPACT 대소문자 무관하게 StructuredFormatter를 반환한다."""
        monkeypatch.setenv("LOG_FORMAT", "COMPACT")
        formatter = get_formatter()
        assert isinstance(formatter, StructuredFormatter)

    def test_case_insensitive_pretty(self, monkeypatch):
        """LOG_FORMAT=PRETTY 대소문자 무관하게 PrettyFormatter를 반환한다."""
        monkeypatch.setenv("LOG_FORMAT", "PRETTY")
        formatter = get_formatter()
        assert isinstance(formatter, PrettyFormatter)

    def test_unknown_value_returns_pretty(self, monkeypatch):
        """알 수 없는 값은 기본값(PrettyFormatter)으로 fallback한다."""
        monkeypatch.setenv("LOG_FORMAT", "unknown_value")
        formatter = get_formatter()
        assert isinstance(formatter, PrettyFormatter)

    def test_returns_logging_formatter(self, monkeypatch):
        """반환값은 항상 logging.Formatter 인스턴스다."""
        monkeypatch.delenv("LOG_FORMAT", raising=False)
        formatter = get_formatter()
        assert isinstance(formatter, logging.Formatter)
