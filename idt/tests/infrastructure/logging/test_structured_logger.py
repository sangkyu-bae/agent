"""Tests for StructuredLogger."""

import json
import logging
import pytest
from io import StringIO

from src.domain.logging.interfaces import LoggerInterface
from src.infrastructure.logging import StructuredLogger
from src.infrastructure.logging.formatters import StructuredFormatter


class TestStructuredLogger:
    """StructuredLogger 테스트."""

    @pytest.fixture
    def log_capture(self):
        """로그 출력 캡처 fixture."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(StructuredFormatter())
        yield stream, handler
        handler.close()

    @pytest.fixture
    def logger(self, log_capture):
        """테스트용 StructuredLogger fixture."""
        stream, handler = log_capture
        logger = StructuredLogger(name="test_logger", level=logging.DEBUG)
        # 기존 핸들러 제거 후 테스트 핸들러만 사용
        logger._logger.handlers.clear()
        logger._logger.addHandler(handler)
        return logger, stream

    def test_structured_logger_implements_logger_interface(self):
        """StructuredLogger는 LoggerInterface를 구현한다."""
        logger = StructuredLogger()
        assert isinstance(logger, LoggerInterface)

    def test_debug_outputs_log(self, logger):
        """debug() 메서드는 DEBUG 레벨 로그를 출력한다."""
        structured_logger, stream = logger
        structured_logger.debug("Debug message")
        output = stream.getvalue()
        parsed = json.loads(output)
        assert parsed["level"] == "DEBUG"
        assert parsed["message"] == "Debug message"

    def test_info_outputs_log(self, logger):
        """info() 메서드는 INFO 레벨 로그를 출력한다."""
        structured_logger, stream = logger
        structured_logger.info("Info message")
        output = stream.getvalue()
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Info message"

    def test_warning_outputs_log(self, logger):
        """warning() 메서드는 WARNING 레벨 로그를 출력한다."""
        structured_logger, stream = logger
        structured_logger.warning("Warning message")
        output = stream.getvalue()
        parsed = json.loads(output)
        assert parsed["level"] == "WARNING"
        assert parsed["message"] == "Warning message"

    def test_error_outputs_log(self, logger):
        """error() 메서드는 ERROR 레벨 로그를 출력한다."""
        structured_logger, stream = logger
        structured_logger.error("Error message")
        output = stream.getvalue()
        parsed = json.loads(output)
        assert parsed["level"] == "ERROR"
        assert parsed["message"] == "Error message"

    def test_critical_outputs_log(self, logger):
        """critical() 메서드는 CRITICAL 레벨 로그를 출력한다."""
        structured_logger, stream = logger
        structured_logger.critical("Critical message")
        output = stream.getvalue()
        parsed = json.loads(output)
        assert parsed["level"] == "CRITICAL"
        assert parsed["message"] == "Critical message"

    def test_error_includes_stacktrace_when_exception_provided(self, logger):
        """error()에 예외가 전달되면 스택 트레이스가 포함된다."""
        structured_logger, stream = logger
        try:
            raise ValueError("Test error")
        except ValueError as e:
            structured_logger.error("Error occurred", exception=e)

        output = stream.getvalue()
        lines = output.split("\n", 1)
        parsed = json.loads(lines[0])

        assert parsed["error_type"] == "ValueError"
        assert parsed["error_message"] == "Test error"
        assert "Traceback" in lines[1]

    def test_critical_includes_stacktrace_when_exception_provided(self, logger):
        """critical()에 예외가 전달되면 스택 트레이스가 포함된다."""
        structured_logger, stream = logger
        try:
            raise RuntimeError("Critical failure")
        except RuntimeError as e:
            structured_logger.critical("Critical error", exception=e)

        output = stream.getvalue()
        lines = output.split("\n", 1)
        parsed = json.loads(lines[0])

        assert parsed["error_type"] == "RuntimeError"
        assert parsed["error_message"] == "Critical failure"
        assert "Traceback" in lines[1]

    def test_kwargs_are_included_in_log(self, logger):
        """kwargs로 전달된 컨텍스트가 로그에 포함된다."""
        structured_logger, stream = logger
        structured_logger.info(
            "Processing request",
            request_id="req-123",
            user_id="user-456",
        )
        output = stream.getvalue()
        parsed = json.loads(output)

        assert parsed["request_id"] == "req-123"
        assert parsed["user_id"] == "user-456"

    def test_logger_name_is_configurable(self):
        """로거 이름을 설정할 수 있다."""
        logger = StructuredLogger(name="custom_logger")
        assert logger._logger.name == "custom_logger"

    def test_logger_level_is_configurable(self, log_capture):
        """로거 레벨을 설정할 수 있다."""
        stream, handler = log_capture
        # 테스트 전용 고유 로거 이름 사용
        logger = StructuredLogger(name="test_level_config", level=logging.WARNING)
        logger._logger.handlers.clear()
        logger._logger.addHandler(handler)

        logger.debug("Debug - should not appear")
        logger.info("Info - should not appear")
        logger.warning("Warning - should appear")

        output = stream.getvalue()
        assert "should not appear" not in output
        assert "should appear" in output
