"""Tests for StructuredFormatter."""

import json
import logging
import pytest

from src.infrastructure.logging.formatters import StructuredFormatter


class TestStructuredFormatter:
    """StructuredFormatter 테스트."""

    def test_formatter_outputs_json(self):
        """포매터는 JSON 형식으로 출력한다."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        # JSON으로 파싱 가능해야 함
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_formatter_includes_timestamp(self):
        """출력에 timestamp 필드가 포함된다."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "timestamp" in parsed

    def test_formatter_includes_level(self):
        """출력에 level 필드가 포함된다."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"

    def test_formatter_includes_logger_name(self):
        """출력에 logger 필드가 포함된다."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="my_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["logger"] == "my_logger"

    def test_formatter_includes_message(self):
        """출력에 message 필드가 포함된다."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "Test message"

    def test_formatter_includes_error_on_exception(self):
        """예외 정보가 있으면 에러 정보와 스택트레이스가 출력된다."""
        formatter = StructuredFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)

        # 첫 번째 줄은 JSON, 나머지는 스택트레이스
        lines = output.split("\n", 1)
        parsed = json.loads(lines[0])

        assert parsed["error_type"] == "ValueError"
        assert parsed["error_message"] == "Test error"
        # 스택트레이스는 별도 줄로 출력됨
        assert len(lines) > 1
        assert "Traceback" in lines[1]

    def test_formatter_includes_extra_fields(self):
        """LogRecord에 추가된 extra 필드가 포함된다."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.request_id = "req-123"
        record.user_id = "user-456"

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["request_id"] == "req-123"
        assert parsed["user_id"] == "user-456"

    def test_formatter_handles_different_log_levels(self):
        """다양한 로그 레벨을 올바르게 처리한다."""
        formatter = StructuredFormatter()
        levels = [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
        ]

        for level, expected_name in levels:
            record = logging.LogRecord(
                name="test",
                level=level,
                pathname="test.py",
                lineno=10,
                msg="Test",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            parsed = json.loads(output)
            assert parsed["level"] == expected_name
