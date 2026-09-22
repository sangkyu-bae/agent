"""Tests for log_context (ContextVar 기반 요청 추적 컨텍스트).

LOG-001 "request_id 컨텍스트 전파" 요구사항의 기반 모듈.
동시 요청 간 격리가 핵심 계약이다.
"""

import asyncio
import uuid

import pytest

from src.domain.logging.value_objects import LogContext
from src.infrastructure.logging.log_context import (
    bind,
    clear,
    get_context_fields,
    get_log_context,
    log_context,
    reset,
)


@pytest.fixture(autouse=True)
def _clean_context():
    """각 테스트가 빈 컨텍스트에서 시작하도록 보장한다."""
    clear()
    yield
    clear()


class TestBindAndGet:
    """bind() / get_context_fields() 기본 동작."""

    def test_empty_context_returns_empty_dict(self):
        """아무것도 바인딩하지 않으면 빈 dict를 반환한다."""
        assert get_context_fields() == {}

    def test_get_log_context_returns_none_when_unbound(self):
        """바인딩 전에는 LogContext가 None이다."""
        assert get_log_context() is None

    def test_bind_sets_request_id(self):
        """bind()로 설정한 request_id가 조회된다."""
        bind(request_id="req-123")
        assert get_context_fields()["request_id"] == "req-123"

    def test_bind_auto_generates_request_id(self):
        """request_id 없이 bind()하면 UUID가 자동 생성된다."""
        bind(endpoint="/api/v1/test")
        request_id = get_context_fields()["request_id"]
        uuid.UUID(request_id)  # UUID 형식이 아니면 ValueError

    def test_bind_sets_known_fields(self):
        """LogContext가 아는 필드는 전용 속성으로 들어간다."""
        bind(
            request_id="req-1",
            user_id="user-1",
            session_id="sess-1",
            endpoint="/api/v1/agents/run",
            method="POST",
        )
        context = get_log_context()
        assert isinstance(context, LogContext)
        assert context.user_id == "user-1"
        assert context.session_id == "sess-1"
        assert context.endpoint == "/api/v1/agents/run"
        assert context.method == "POST"

    def test_bind_routes_unknown_fields_to_extra(self):
        """LogContext가 모르는 필드는 extra로 들어간다."""
        bind(request_id="req-1", agent_run_id="run-99")
        context = get_log_context()
        assert context.extra == {"agent_run_id": "run-99"}
        assert get_context_fields()["agent_run_id"] == "run-99"

    def test_returned_fields_are_a_copy(self):
        """반환된 dict를 변경해도 컨텍스트는 오염되지 않는다."""
        bind(request_id="req-1")
        fields = get_context_fields()
        fields["request_id"] = "tampered"
        assert get_context_fields()["request_id"] == "req-1"


class TestBindMerging:
    """bind() 중첩 시 병합 규칙."""

    def test_second_bind_preserves_earlier_fields(self):
        """나중 bind()는 기존 필드를 유지한다."""
        bind(request_id="req-1", endpoint="/a")
        bind(user_id="user-1")
        fields = get_context_fields()
        assert fields["request_id"] == "req-1"
        assert fields["endpoint"] == "/a"
        assert fields["user_id"] == "user-1"

    def test_second_bind_overwrites_same_field(self):
        """같은 필드를 다시 bind()하면 나중 값이 이긴다."""
        bind(user_id="user-1")
        bind(user_id="user-2")
        assert get_context_fields()["user_id"] == "user-2"

    def test_second_bind_merges_extra(self):
        """extra 필드도 누적 병합된다."""
        bind(request_id="req-1", agent_run_id="run-1")
        bind(node_name="search")
        fields = get_context_fields()
        assert fields["agent_run_id"] == "run-1"
        assert fields["node_name"] == "search"

    def test_bind_does_not_mutate_previous_context(self):
        """bind()는 이전 LogContext 인스턴스를 변경하지 않는다 (불변)."""
        bind(request_id="req-1")
        before = get_log_context()
        bind(user_id="user-1")
        assert before.user_id is None


class TestResetAndClear:
    """reset() / clear() 복원 동작."""

    def test_reset_restores_previous_context(self):
        """reset(token)은 bind 직전 상태로 되돌린다."""
        bind(request_id="req-1")
        token = bind(user_id="user-1")
        reset(token)
        fields = get_context_fields()
        assert fields["request_id"] == "req-1"
        assert "user_id" not in fields

    def test_reset_to_empty(self):
        """최초 bind의 토큰으로 reset하면 빈 컨텍스트로 돌아간다."""
        token = bind(request_id="req-1")
        reset(token)
        assert get_context_fields() == {}

    def test_clear_empties_context(self):
        """clear()는 컨텍스트를 비운다."""
        bind(request_id="req-1", user_id="user-1")
        clear()
        assert get_context_fields() == {}


class TestLogContextManager:
    """log_context() 컨텍스트 매니저."""

    def test_fields_visible_inside_block(self):
        """with 블록 안에서는 필드가 보인다."""
        with log_context(request_id="req-1", endpoint="/a"):
            assert get_context_fields()["endpoint"] == "/a"

    def test_context_restored_after_block(self):
        """with 블록을 벗어나면 이전 상태로 복원된다."""
        with log_context(request_id="req-1"):
            pass
        assert get_context_fields() == {}

    def test_context_restored_on_exception(self):
        """예외가 나도 컨텍스트는 복원된다."""
        with pytest.raises(ValueError):
            with log_context(request_id="req-1"):
                raise ValueError("boom")
        assert get_context_fields() == {}

    def test_nested_blocks_merge_then_restore(self):
        """중첩 블록은 병합되고, 안쪽을 벗어나면 바깥 상태만 남는다."""
        with log_context(request_id="req-1"):
            with log_context(user_id="user-1"):
                assert get_context_fields()["user_id"] == "user-1"
                assert get_context_fields()["request_id"] == "req-1"
            assert "user_id" not in get_context_fields()


class TestConcurrentIsolation:
    """동시 실행 태스크 간 격리 — 이 모듈의 존재 이유."""

    @pytest.mark.asyncio
    async def test_concurrent_tasks_do_not_leak_context(self):
        """gather로 동시 실행된 태스크는 서로의 request_id를 보지 않는다."""

        async def handler(request_id: str) -> str:
            bind(request_id=request_id)
            await asyncio.sleep(0)  # 다른 태스크에 제어권 양보
            return get_context_fields()["request_id"]

        results = await asyncio.gather(
            handler("REQ-A"), handler("REQ-B"), handler("REQ-C")
        )
        assert results == ["REQ-A", "REQ-B", "REQ-C"]

    @pytest.mark.asyncio
    async def test_child_task_inherits_parent_context(self):
        """자식 태스크는 부모의 컨텍스트를 물려받는다."""
        bind(request_id="REQ-PARENT")

        async def child() -> str:
            return get_context_fields()["request_id"]

        assert await asyncio.create_task(child()) == "REQ-PARENT"

    @pytest.mark.asyncio
    async def test_child_bind_does_not_affect_parent(self):
        """자식 태스크의 bind는 부모 컨텍스트를 오염시키지 않는다."""
        bind(request_id="REQ-PARENT")

        async def child() -> None:
            bind(request_id="REQ-CHILD")

        await asyncio.create_task(child())
        assert get_context_fields()["request_id"] == "REQ-PARENT"
