"""Tests for PrettyFormatter."""

import logging
import pytest

from src.infrastructure.logging.formatters import PrettyFormatter


def _make_record(
    msg="Test message",
    level=logging.INFO,
    name="test_logger",
    filename="test.py",
    funcname="test_func",
    lineno=42,
    exc_info=None,
    **extra,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname=filename,
        lineno=lineno,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )
    record.funcName = funcname
    record.filename = filename
    # extra 필드 주입
    for k, v in extra.items():
        setattr(record, k, v)
    return record


class TestPrettyFormatterStructure:
    """PrettyFormatter 출력 구조 테스트."""

    def test_contains_separator(self):
        """출력에 구분선(─)이 포함된다."""
        formatter = PrettyFormatter()
        record = _make_record()
        output = formatter.format(record)
        assert "─" in output

    def test_contains_message(self):
        """출력에 로그 메시지가 포함된다."""
        formatter = PrettyFormatter()
        record = _make_record(msg="Hello world")
        output = formatter.format(record)
        assert "Hello world" in output

    def test_contains_level(self):
        """출력에 로그 레벨이 포함된다."""
        formatter = PrettyFormatter()
        record = _make_record(level=logging.INFO)
        output = formatter.format(record)
        assert "INFO" in output

    def test_contains_timestamp(self):
        """출력에 타임스탬프(Z 접미사)가 포함된다."""
        formatter = PrettyFormatter()
        record = _make_record()
        output = formatter.format(record)
        assert "Z" in output  # UTC 타임스탬프 형식

    def test_contains_location(self):
        """출력에 파일명:함수명:라인 위치가 포함된다."""
        formatter = PrettyFormatter()
        record = _make_record(filename="myfile.py", funcname="my_func", lineno=99)
        output = formatter.format(record)
        assert "myfile.py" in output
        assert "my_func" in output
        assert "99" in output

    def test_is_multiline(self):
        """출력은 멀티라인이다 (개행 문자 포함)."""
        formatter = PrettyFormatter()
        record = _make_record()
        output = formatter.format(record)
        assert "\n" in output


class TestPrettyFormatterExtraFields:
    """PrettyFormatter extra 필드 출력 테스트."""

    def test_extra_field_included(self):
        """extra 필드가 출력에 포함된다."""
        formatter = PrettyFormatter()
        record = _make_record(request_id="abc-123")
        output = formatter.format(record)
        assert "request_id" in output
        assert "abc-123" in output

    def test_extra_field_indented(self):
        """extra 필드는 들여쓰기(공백 2칸)로 시작한다."""
        formatter = PrettyFormatter()
        record = _make_record(endpoint="/api/test")
        output = formatter.format(record)
        # 들여쓰기된 필드 라인 존재 여부
        lines = output.split("\n")
        indented_lines = [l for l in lines if l.startswith("  ")]
        assert len(indented_lines) > 0

    def test_multiple_extra_fields(self):
        """여러 extra 필드가 모두 출력된다."""
        formatter = PrettyFormatter()
        record = _make_record(
            request_id="req-1",
            method="POST",
            status_code=200,
        )
        output = formatter.format(record)
        assert "request_id" in output
        assert "method" in output
        assert "status_code" in output

    def test_reserved_attrs_not_in_fields(self):
        """Python logging 예약 속성은 extra 필드로 출력되지 않는다."""
        formatter = PrettyFormatter()
        record = _make_record()
        output = formatter.format(record)
        # 예약 속성들이 별도 필드 라인으로 나오지 않아야 함
        lines = output.split("\n")
        field_lines = [l for l in lines if l.startswith("  ") and " : " in l]
        field_keys = [l.strip().split(" : ")[0].strip() for l in field_lines]
        reserved = {"name", "msg", "args", "levelname", "levelno", "lineno", "module"}
        for key in field_keys:
            assert key not in reserved


class TestPrettyFormatterLevels:
    """PrettyFormatter 로그 레벨별 테스트."""

    @pytest.mark.parametrize("level,levelname", [
        (logging.DEBUG, "DEBUG"),
        (logging.INFO, "INFO"),
        (logging.WARNING, "WARNING"),
        (logging.ERROR, "ERROR"),
        (logging.CRITICAL, "CRITICAL"),
    ])
    def test_level_name_in_output(self, level, levelname):
        """각 로그 레벨명이 출력에 포함된다."""
        formatter = PrettyFormatter()
        record = _make_record(level=level)
        output = formatter.format(record)
        assert levelname in output


class TestPrettyFormatterError:
    """PrettyFormatter 에러/예외 처리 테스트."""

    def test_error_with_stacktrace(self):
        """exc_info가 있을 때 스택트레이스가 출력에 포함된다."""
        formatter = PrettyFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = _make_record(level=logging.ERROR, exc_info=exc_info)
        output = formatter.format(record)
        assert "ValueError" in output
        assert "test error" in output
        assert "Traceback" in output

    def test_no_exc_info_no_stacktrace(self):
        """exc_info가 없을 때 Traceback이 출력에 포함되지 않는다."""
        formatter = PrettyFormatter()
        record = _make_record(exc_info=None)
        output = formatter.format(record)
        assert "Traceback" not in output
