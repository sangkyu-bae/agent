"""Tests for LogContext Value Object."""

import pytest
import uuid

from src.domain.logging.value_objects import LogContext


class TestLogContext:
    """LogContext Value Object 테스트."""

    def test_request_id_auto_generated_when_not_provided(self):
        """request_id가 제공되지 않으면 자동 생성된다."""
        context = LogContext()
        assert context.request_id is not None
        # UUID 형식 확인
        uuid.UUID(context.request_id)

    def test_request_id_can_be_set_explicitly(self):
        """request_id를 명시적으로 설정할 수 있다."""
        custom_id = "custom-request-id-123"
        context = LogContext(request_id=custom_id)
        assert context.request_id == custom_id

    def test_user_id_can_be_set(self):
        """user_id를 설정할 수 있다."""
        context = LogContext(user_id="user-123")
        assert context.user_id == "user-123"

    def test_session_id_can_be_set(self):
        """session_id를 설정할 수 있다."""
        context = LogContext(session_id="session-456")
        assert context.session_id == "session-456"

    def test_endpoint_can_be_set(self):
        """endpoint를 설정할 수 있다."""
        context = LogContext(endpoint="/api/v1/documents")
        assert context.endpoint == "/api/v1/documents"

    def test_method_can_be_set(self):
        """method를 설정할 수 있다."""
        context = LogContext(method="POST")
        assert context.method == "POST"

    def test_to_dict_returns_all_fields(self):
        """to_dict()는 모든 필드를 딕셔너리로 반환한다."""
        context = LogContext(
            request_id="req-123",
            user_id="user-456",
            session_id="session-789",
            endpoint="/api/v1/test",
            method="GET",
        )
        result = context.to_dict()

        assert result["request_id"] == "req-123"
        assert result["user_id"] == "user-456"
        assert result["session_id"] == "session-789"
        assert result["endpoint"] == "/api/v1/test"
        assert result["method"] == "GET"

    def test_to_dict_excludes_none_values(self):
        """to_dict()는 None 값을 제외한다."""
        context = LogContext(request_id="req-123")
        result = context.to_dict()

        assert "request_id" in result
        assert "user_id" not in result
        assert "session_id" not in result
        assert "endpoint" not in result
        assert "method" not in result

    def test_log_context_is_immutable(self):
        """LogContext는 불변이어야 한다 (frozen dataclass)."""
        context = LogContext(request_id="req-123")
        with pytest.raises(AttributeError):
            context.request_id = "new-id"

    def test_two_contexts_with_same_values_are_equal(self):
        """동일한 값을 가진 두 컨텍스트는 동등하다."""
        context1 = LogContext(
            request_id="req-123",
            user_id="user-456",
        )
        context2 = LogContext(
            request_id="req-123",
            user_id="user-456",
        )
        assert context1 == context2

    def test_extra_fields_can_be_added(self):
        """추가 필드를 설정할 수 있다."""
        context = LogContext(
            request_id="req-123",
            extra={"custom_field": "value", "another": 123},
        )
        result = context.to_dict()
        assert result["custom_field"] == "value"
        assert result["another"] == 123
