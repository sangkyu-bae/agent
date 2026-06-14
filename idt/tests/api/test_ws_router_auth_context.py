"""WS 엔드포인트 AuthContext 전달 통합 테스트.

fix-ws-auth-context-missing Design §3.4.1 검증:
- /ws/agent 와 /ws/chat 이 조립한 AuthContext를 stream(auth_ctx=...)로 전달
- viewer_department_ids == list(auth_ctx.department_ids)
- 조립 실패 시 anonymous로 degrade (fail-closed), 연결은 유지
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.routes.ws_router import (
    router,
    get_connection_manager,
    get_ws_jwt_adapter,
    get_ws_user_repository,
    get_ws_run_agent_use_case,
    get_ws_general_chat_use_case,
    get_chat_stream_cache,
    get_ws_auth_context_resolver,
    get_ws_logger,
)
from src.domain.agent_run.auth_context import AuthContext
from src.domain.agent_run.value_objects import AgentRunEvent, AgentRunEventType
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.auth.value_objects import TokenPayload
from src.domain.general_chat.interfaces import ChatStreamCacheInterface
from src.domain.general_chat.value_objects import ChatEvent, ChatEventType
from src.infrastructure.websocket.connection_manager import ConnectionManager


def _fake_user(user_id: int = 1) -> User:
    return User(
        email="t@t.com", password_hash="h",
        role=UserRole.USER, status=UserStatus.APPROVED, id=user_id,
    )


def _auth_ctx() -> AuthContext:
    return AuthContext(
        user_id=1,
        display_name="홍길동",
        role="user",
        primary_department_id="d1",
        primary_department_name="여신심사부",
        department_ids=("d1", "d2"),
        department_names=("여신심사부", "리스크부"),
        permissions=frozenset({"USE_RAG_SEARCH"}),
    )


def _make_jwt_adapter() -> MagicMock:
    a = MagicMock()
    a.decode.return_value = TokenPayload(
        sub="1", role="user", token_type="access", exp=9999999999
    )
    return a


def _make_user_repo() -> MagicMock:
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=_fake_user())
    return repo


def _make_resolver(auth_ctx: AuthContext | None = None, raises: Exception | None = None):
    r = MagicMock()

    async def _execute(user, request_id):
        if raises is not None:
            raise raises
        return auth_ctx if auth_ctx is not None else _auth_ctx()

    r.execute = _execute
    return r


def _recording_agent_uc():
    calls: dict = {}
    uc = MagicMock()

    def _stream(*args, **kwargs):
        calls.update(kwargs)
        calls["_args"] = args

        async def _gen():
            yield AgentRunEvent(
                seq=1, event_type=AgentRunEventType.RUN_COMPLETED,
                run_id="rid", payload={"run_id": "rid", "langsmith_run_url": None},
                timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )
        return _gen()

    uc.stream = _stream
    return uc, calls


def _recording_chat_uc():
    calls: dict = {}
    uc = MagicMock()

    def _stream(*args, **kwargs):
        calls.update(kwargs)
        calls["_args"] = args

        async def _gen():
            yield ChatEvent(
                seq=1, event_type=ChatEventType.CHAT_DONE,
                session_id="s-1", payload={"session_id": "s-1"},
                timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )
        return _gen()

    uc.stream = _stream
    return uc, calls


class _FakeCache(ChatStreamCacheInterface):
    async def record(self, sid, ev):  # type: ignore[override]
        pass

    async def replay(self, sid):  # type: ignore[override]
        return []

    async def clear(self, sid):  # type: ignore[override]
        pass


def _base_app(resolver) -> tuple[FastAPI, MagicMock]:
    app = FastAPI()
    app.include_router(router)
    logger = MagicMock()
    manager = ConnectionManager(logger=logger)
    app.dependency_overrides[get_connection_manager] = lambda: manager
    app.dependency_overrides[get_ws_jwt_adapter] = _make_jwt_adapter
    app.dependency_overrides[get_ws_user_repository] = _make_user_repo
    app.dependency_overrides[get_ws_auth_context_resolver] = lambda: resolver
    app.dependency_overrides[get_ws_logger] = lambda: logger
    return app, logger


class TestAgentRunAuthContext:
    def test_passes_assembled_auth_context_and_department_ids(self) -> None:
        uc, calls = _recording_agent_uc()
        app, _ = _base_app(_make_resolver())
        app.dependency_overrides[get_ws_run_agent_use_case] = lambda: uc
        client = TestClient(app)

        with client.websocket_connect("/ws/agent/rid?token=t") as ws:
            ws.send_json({"type": "subscribe", "agent_id": "a", "query": "hi"})
            ws.receive_json()  # run_completed
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

        assert "auth_ctx" in calls
        assert isinstance(calls["auth_ctx"], AuthContext)
        assert calls["auth_ctx"].display_name == "홍길동"
        assert calls["viewer_department_ids"] == ["d1", "d2"]

    def test_assembly_failure_degrades_to_anonymous(self) -> None:
        uc, calls = _recording_agent_uc()
        resolver = _make_resolver(raises=RuntimeError("db down"))
        app, logger = _base_app(resolver)
        app.dependency_overrides[get_ws_run_agent_use_case] = lambda: uc
        client = TestClient(app)

        with client.websocket_connect("/ws/agent/rid?token=t") as ws:
            ws.send_json({"type": "subscribe", "agent_id": "a", "query": "hi"})
            ws.receive_json()  # run_completed — 연결 정상 진행
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

        assert calls["auth_ctx"].role == "anonymous"
        assert calls["auth_ctx"].permissions == frozenset()
        assert calls["viewer_department_ids"] == []
        logger.error.assert_called()


class TestChatAuthContext:
    def test_passes_assembled_auth_context(self) -> None:
        uc, calls = _recording_chat_uc()
        app, _ = _base_app(_make_resolver())
        app.dependency_overrides[get_ws_general_chat_use_case] = lambda: uc
        app.dependency_overrides[get_chat_stream_cache] = lambda: _FakeCache()
        client = TestClient(app)

        with client.websocket_connect("/ws/chat/s-1?token=t") as ws:
            ws.send_json({"type": "subscribe", "message": "안녕"})
            ws.receive_json()  # chat_done
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

        assert "auth_ctx" in calls
        assert isinstance(calls["auth_ctx"], AuthContext)
        assert calls["auth_ctx"].display_name == "홍길동"
