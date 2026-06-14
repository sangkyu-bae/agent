"""GET /api/v1/agents/{agent_id}/run/stream — SSE 엔드포인트 통합 테스트.

Design §5.5 / §8.3 (agent-run-streaming-sse).
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_builder_router import (
    router,
    get_run_agent_use_case,
)
from src.domain.agent_run.value_objects import (
    AgentRunEvent,
    AgentRunEventType,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user_from_query_token


def _fake_user(user_id: int = 1) -> User:
    return User(
        email="t@t.com", password_hash="h",
        role=UserRole.USER, status=UserStatus.APPROVED, id=user_id,
    )


def _ev(seq: int, et: AgentRunEventType, payload: dict, run_id: str | None = "rid"):
    return AgentRunEvent(
        seq=seq,
        event_type=et,
        run_id=run_id,
        payload=payload,
        timestamp=datetime(2026, 5, 24, tzinfo=timezone.utc),
    )


def _make_uc_yielding(events: list[AgentRunEvent]):
    """stream()이 주어진 events를 yield하는 mock UseCase."""
    uc = MagicMock()

    def _stream(*args, **kwargs):
        async def _gen():
            for e in events:
                yield e
        return _gen()

    uc.stream = _stream
    uc.execute = AsyncMock()  # not used by GET /run/stream
    return uc


def _make_uc_raising(exc: Exception):
    """stream()이 첫 anext에서 예외 발생하는 mock UseCase."""
    uc = MagicMock()

    def _stream(*args, **kwargs):
        async def _gen():
            raise exc
            yield  # unreachable; make async generator
        return _gen()

    uc.stream = _stream
    return uc


def _make_app(use_case, user: User | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_run_agent_use_case] = lambda: use_case
    app.dependency_overrides[get_current_user_from_query_token] = (
        lambda: user if user is not None else _fake_user()
    )
    return app


# ── 기본 성공 케이스 ────────────────────────────────────────────────────


class TestStreamEndpointHappyPath:
    def test_returns_200_with_sse_content_type(self):
        agent_id = str(uuid.uuid4())
        events = [
            _ev(1, AgentRunEventType.RUN_STARTED,
                {"run_id": "rid", "session_id": "s", "agent_id": agent_id}),
            _ev(2, AgentRunEventType.ANSWER_COMPLETED,
                {"answer": "ok", "tools_used": []}),
            _ev(3, AgentRunEventType.RUN_COMPLETED,
                {"run_id": "rid", "langsmith_run_url": None}),
        ]
        client = TestClient(_make_app(_make_uc_yielding(events)))

        resp = client.get(
            f"/api/v1/agents/{agent_id}/run/stream",
            params={"query": "hi", "user_id": "1", "token": "valid"},
        )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers.get("cache-control") == "no-cache, no-transform"
        assert resp.headers.get("x-accel-buffering") == "no"

    def test_first_line_is_run_started(self):
        agent_id = str(uuid.uuid4())
        events = [
            _ev(1, AgentRunEventType.RUN_STARTED,
                {"run_id": "rid", "session_id": "s", "agent_id": agent_id}),
            _ev(2, AgentRunEventType.RUN_COMPLETED,
                {"run_id": "rid", "langsmith_run_url": None}),
        ]
        client = TestClient(_make_app(_make_uc_yielding(events)))

        resp = client.get(
            f"/api/v1/agents/{agent_id}/run/stream",
            params={"query": "hi", "user_id": "1", "token": "valid"},
        )

        assert resp.text.startswith("event: run_started\n")

    def test_body_contains_all_event_types(self):
        agent_id = str(uuid.uuid4())
        events = [
            _ev(1, AgentRunEventType.RUN_STARTED,
                {"run_id": "rid", "session_id": "s", "agent_id": agent_id}),
            _ev(2, AgentRunEventType.NODE_STARTED,
                {"node_name": "supervisor", "node_type": "SUPERVISOR"}),
            _ev(3, AgentRunEventType.ANSWER_COMPLETED,
                {"answer": "안녕", "tools_used": []}),
            _ev(4, AgentRunEventType.RUN_COMPLETED,
                {"run_id": "rid", "langsmith_run_url": None}),
        ]
        client = TestClient(_make_app(_make_uc_yielding(events)))

        resp = client.get(
            f"/api/v1/agents/{agent_id}/run/stream",
            params={"query": "hi", "user_id": "1", "token": "valid"},
        )

        assert "event: run_started" in resp.text
        assert "event: node_started" in resp.text
        assert "event: answer_completed" in resp.text
        assert "event: run_completed" in resp.text
        # 한글 escape 안됨
        assert "안녕" in resp.text


# ── 인증 / 권한 ─────────────────────────────────────────────────────────


class TestStreamEndpointAuth:
    def test_missing_token_returns_422(self):
        # FastAPI Query(...) required → 토큰 미제공 시 422
        # 모든 sub-dep placeholder가 NotImplementedError 던지지 않도록 override
        from src.interfaces.dependencies.auth import (
            get_jwt_adapter,
            get_user_repository,
        )
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_jwt_adapter] = lambda: MagicMock()
        app.dependency_overrides[get_user_repository] = lambda: MagicMock()
        app.dependency_overrides[get_run_agent_use_case] = (
            lambda: _make_uc_yielding([])
        )
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get(
            f"/api/v1/agents/{uuid.uuid4()}/run/stream",
            params={"query": "x", "user_id": "1"},  # no token
        )

        assert resp.status_code == 422  # Query(...) validation

    def test_user_id_mismatch_with_token_sub_returns_403(self):
        agent_id = str(uuid.uuid4())
        # token sub == user 1, but query user_id == "99"
        client = TestClient(_make_app(_make_uc_yielding([]), user=_fake_user(1)))

        resp = client.get(
            f"/api/v1/agents/{agent_id}/run/stream",
            params={"query": "x", "user_id": "99", "token": "valid"},
        )

        assert resp.status_code == 403


# ── 에러 처리 ────────────────────────────────────────────────────────────


class TestStreamEndpointErrorPaths:
    def test_agent_not_found_yields_run_failed_event(self):
        agent_id = str(uuid.uuid4())
        client = TestClient(_make_app(
            _make_uc_raising(ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}"))
        ))

        resp = client.get(
            f"/api/v1/agents/{agent_id}/run/stream",
            params={"query": "x", "user_id": "1", "token": "valid"},
        )

        assert resp.status_code == 200
        assert "event: run_failed" in resp.text
        assert "AGENT_NOT_FOUND" in resp.text or "찾을 수 없" in resp.text

    def test_permission_denied_yields_run_failed_event(self):
        agent_id = str(uuid.uuid4())
        client = TestClient(_make_app(
            _make_uc_raising(PermissionError("이 에이전트에 대한 실행 권한이 없습니다"))
        ))

        resp = client.get(
            f"/api/v1/agents/{agent_id}/run/stream",
            params={"query": "x", "user_id": "1", "token": "valid"},
        )

        assert resp.status_code == 200
        assert "event: run_failed" in resp.text
        assert "PERMISSION_DENIED" in resp.text or "권한 없" in resp.text


# ── 쿼리 파라미터 검증 ────────────────────────────────────────────────


class TestStreamEndpointQueryValidation:
    def test_empty_query_returns_422(self):
        client = TestClient(_make_app(_make_uc_yielding([])))

        resp = client.get(
            f"/api/v1/agents/{uuid.uuid4()}/run/stream",
            params={"query": "", "user_id": "1", "token": "valid"},
        )

        assert resp.status_code == 422

    def test_too_long_query_returns_422(self):
        client = TestClient(_make_app(_make_uc_yielding([])))

        resp = client.get(
            f"/api/v1/agents/{uuid.uuid4()}/run/stream",
            params={"query": "x" * 5000, "user_id": "1", "token": "valid"},
        )

        assert resp.status_code == 422
