"""Tests for ErrorSchema."""

import pytest
from pydantic import ValidationError

from src.domain.logging.schemas import ErrorDetail, ErrorResponse


class TestErrorDetail:
    """ErrorDetail 스키마 테스트."""

    def test_error_detail_with_all_fields(self):
        """모든 필드가 설정된 ErrorDetail을 생성할 수 있다."""
        error = ErrorDetail(
            type="ValueError",
            message="Invalid input",
            stacktrace="Traceback...",
        )
        assert error.type == "ValueError"
        assert error.message == "Invalid input"
        assert error.stacktrace == "Traceback..."

    def test_error_detail_without_stacktrace(self):
        """stacktrace 없이 ErrorDetail을 생성할 수 있다."""
        error = ErrorDetail(
            type="ValueError",
            message="Invalid input",
        )
        assert error.type == "ValueError"
        assert error.message == "Invalid input"
        assert error.stacktrace is None

    def test_error_detail_type_is_required(self):
        """type은 필수 필드이다."""
        with pytest.raises(ValidationError):
            ErrorDetail(message="Invalid input")

    def test_error_detail_message_is_required(self):
        """message는 필수 필드이다."""
        with pytest.raises(ValidationError):
            ErrorDetail(type="ValueError")


class TestErrorResponse:
    """ErrorResponse 스키마 테스트."""

    def test_error_response_with_all_fields(self):
        """모든 필드가 설정된 ErrorResponse를 생성할 수 있다."""
        error_detail = ErrorDetail(
            type="ValueError",
            message="Invalid input",
            stacktrace="Traceback...",
        )
        response = ErrorResponse(
            request_id="req-123",
            error=error_detail,
        )
        assert response.request_id == "req-123"
        assert response.error.type == "ValueError"
        assert response.error.message == "Invalid input"
        assert response.error.stacktrace == "Traceback..."

    def test_error_response_request_id_is_required(self):
        """request_id는 필수 필드이다."""
        error_detail = ErrorDetail(
            type="ValueError",
            message="Invalid input",
        )
        with pytest.raises(ValidationError):
            ErrorResponse(error=error_detail)

    def test_error_response_error_is_required(self):
        """error는 필수 필드이다."""
        with pytest.raises(ValidationError):
            ErrorResponse(request_id="req-123")

    def test_error_response_to_dict(self):
        """ErrorResponse를 dict로 변환할 수 있다."""
        error_detail = ErrorDetail(
            type="ValueError",
            message="Invalid input",
        )
        response = ErrorResponse(
            request_id="req-123",
            error=error_detail,
        )
        result = response.model_dump()

        assert result["request_id"] == "req-123"
        assert result["error"]["type"] == "ValueError"
        assert result["error"]["message"] == "Invalid input"

    def test_error_response_excludes_none_stacktrace(self):
        """stacktrace가 None이면 제외된다 (exclude_none 옵션 사용 시)."""
        error_detail = ErrorDetail(
            type="ValueError",
            message="Invalid input",
        )
        response = ErrorResponse(
            request_id="req-123",
            error=error_detail,
        )
        result = response.model_dump(exclude_none=True)

        assert "stacktrace" not in result["error"]
