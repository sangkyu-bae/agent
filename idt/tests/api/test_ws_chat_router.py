"""WS /ws/chat/{session_id} 엔드포인트 통합 테스트.

Design ws-chat-streaming §4.3.
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
    get_ws_general_chat_use_case,
    get_chat_stream_cache,
    get_ws_auth_context_resolver,
    get_ws_logger,
)
from src.domain.agent_run.auth_context import AuthContext
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.auth.value_objects import TokenPayload
from src.domain.general_chat.value_objects import ChatEvent, ChatEventType
from src.domain.general_chat.interfaces import ChatStreamCacheInterface
from src.domain.websocket.schemas import WSCloseCode
from src.infrastructure.websocket.connection_manager import ConnectionManager


def _fake_user(user_id: int = 1) -> User:
    return User(
        email="t@t.com", password_hash="h",
        role=UserRole.USER, status=UserStatus.APPROVED, id=user_id,
    )


def _ev(seq: int, et: ChatEventType, payload: dict, sid: str = "s-1") -> ChatEvent:
    return ChatEvent(
        seq=seq, event_type=et, session_id=sid,
        payload=payload,
        timestamp=datetime(2026, 5, 25, tzinfo=timezone.utc),
    )


def _make_uc_yielding(events: list[ChatEvent]):
    uc = MagicMock()

    def _stream(*args, **kwargs):
        async def _gen():
            for e in events:
                yield e
        return _gen()

    uc.stream = _stream
    return uc


def _make_uc_raising(exc: Exception):
    uc = MagicMock()

    def _stream(*args, **kwargs):
        async def _gen():
            raise exc
            yield  # unreachable

        return _gen()

    uc.stream = _stream
    return uc


def _make_jwt_adapter(token_type: str = "access", user_id: str = "1") -> MagicMock:
    a = MagicMock()
    a.decode.return_value = TokenPayload(
        sub=user_id, role="user", token_type=token_type, exp=9999999999
    )
    return a


def _make_user_repo(user: User | None = None) -> MagicMock:
    repo = MagicMock()
    repo.find_by_id = AsyncMock(
        return_value=user if user is not None else _fake_user()
    )
    return repo


def _make_auth_resolver() -> MagicMock:
    resolver = MagicMock()

    async def _execute(user, request_id):
        return AuthContext(
            user_id=user.id or 1,
            display_name="tester",
            role="user",
            primary_department_id=None,
            primary_department_name=None,
            department_ids=(),
            department_names=(),
            permissions=frozenset(),
        )

    resolver.execute = _execute
    return resolver


class _FakeCache(ChatStreamCacheInterface):
    def __init__(self, initial: dict[str, list[ChatEvent]] | None = None) -> None:
        self._data: dict[str, list[ChatEvent]] = initial or {}
        self.record_calls: list[tuple[str, ChatEvent]] = []
        self.clear_calls: list[str] = []

    async def record(self, sid, ev):  # type: ignore[override]
        self._data.setdefault(sid, []).append(ev)
        self.record_calls.append((sid, ev))

    async def replay(self, sid):  # type: ignore[override]
        return list(self._data.get(sid, []))

    async def clear(self, sid):  # type: ignore[override]
        self._data.pop(sid, None)
        self.clear_calls.append(sid)


def _make_app(
    use_case,
    user: User | None = None,
    jwt_adapter: MagicMock | None = None,
    cache: _FakeCache | None = None,
) -> tuple[FastAPI, _FakeCache]:
    app = FastAPI()
    app.include_router(router)
    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    manager = ConnectionManager(logger=logger)
    cache = cache or _FakeCache()

    app.dependency_overrides[get_connection_manager] = lambda: manager
    app.dependency_overrides[get_ws_jwt_adapter] = (
        lambda: jwt_adapter if jwt_adapter is not None else _make_jwt_adapter()
    )
    app.dependency_overrides[get_ws_user_repository] = lambda: _make_user_repo(user)
    app.dependency_overrides[get_ws_general_chat_use_case] = lambda: use_case
    app.dependency_overrides[get_chat_stream_cache] = lambda: cache
    app.dependency_overrides[get_ws_auth_context_resolver] = _make_auth_resolver
    app.dependency_overrides[get_ws_logger] = lambda: logger
    return app, cache


class TestAuth:
    def test_no_token_closes_4001(self) -> None:
        app, _ = _make_app(use_case=_make_uc_yielding([]))
        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/chat/s-1") as ws:
                ws.receive_json()
        assert exc.value.code == WSCloseCode.AUTH_FAILED


class TestSubscribeValidation:
    def test_invalid_payload_rejected_with_forbidden(self) -> None:
        app, _ = _make_app(use_case=_make_uc_yielding([]))
        client = TestClient(app)
        with client.websocket_connect("/ws/chat/s-1?token=t") as ws:
            ws.send_json({"type": "wrong", "message": "x"})
            err = ws.receive_json()
            assert err["type"] == "error"
            assert err["data"]["code"] == "INVALID_SUBSCRIBE"
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()


class TestHappyPath:
    def test_full_sequence(self) -> None:
        events = [
            _ev(1, ChatEventType.CHAT_STARTED, {"session_id": "s-1"}),
            _ev(2, ChatEventType.TOKEN, {"chunk": "안"}),
            _ev(3, ChatEventType.TOKEN, {"chunk": "녕"}),
            _ev(4, ChatEventType.ANSWER_COMPLETED, {
                "answer": "안녕하세요",
                "tools_used": [],
                "sources": [],
                "was_summarized": False,
            }),
            _ev(5, ChatEventType.CHAT_DONE, {"session_id": "s-1"}),
        ]
        app, cache = _make_app(use_case=_make_uc_yielding(events))
        client = TestClient(app)

        with client.websocket_connect("/ws/chat/s-1?token=t") as ws:
            ws.send_json({"type": "subscribe", "message": "안녕"})
            msgs = [ws.receive_json() for _ in range(5)]
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()

        types = [m["type"] for m in msgs]
        assert types == [
            "chat_started", "chat_token", "chat_token",
            "chat_answer_completed", "chat_done",
        ]
        assert msgs[1]["data"]["chunk"] == "안"
        assert msgs[1]["metadata"]["seq"] == 2
        assert exc.value.code == WSCloseCode.NORMAL
        # cache는 record 5번 + CHAT_DONE 후 clear 1번
        assert len(cache.record_calls) == 5
        assert cache.clear_calls == ["s-1"]


class TestReplay:
    def test_replay_events_first_with_cached_metadata(self) -> None:
        # 진행 중인 stream이 cache에 있다고 가정
        cached = [
            _ev(1, ChatEventType.CHAT_STARTED, {"session_id": "s-1"}),
            _ev(2, ChatEventType.TOKEN, {"chunk": "이전"}),
        ]
        cache = _FakeCache(initial={"s-1": cached})

        # 새 subscribe 후 새 이벤트
        new_events = [
            _ev(3, ChatEventType.TOKEN, {"chunk": "신규"}),
            _ev(4, ChatEventType.ANSWER_COMPLETED, {
                "answer": "이전신규", "tools_used": [], "sources": [],
                "was_summarized": False,
            }),
            _ev(5, ChatEventType.CHAT_DONE, {"session_id": "s-1"}),
        ]
        app, _ = _make_app(use_case=_make_uc_yielding(new_events), cache=cache)
        client = TestClient(app)

        with client.websocket_connect("/ws/chat/s-1?token=t") as ws:
            # 첫 2개는 cached
            r1 = ws.receive_json()
            r2 = ws.receive_json()
            assert r1["metadata"]["cached"] is True
            assert r2["metadata"]["cached"] is True
            assert r1["type"] == "chat_started"
            assert r2["data"]["chunk"] == "이전"

            # subscribe → 새 이벤트
            ws.send_json({"type": "subscribe", "message": "안녕"})
            n3 = ws.receive_json()
            n4 = ws.receive_json()
            n5 = ws.receive_json()
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

        assert n3["data"]["chunk"] == "신규"
        assert "cached" not in n3["metadata"]


class TestErrorPath:
    def test_chat_failed_event_propagated_and_clears_cache(self) -> None:
        events = [
            _ev(1, ChatEventType.CHAT_STARTED, {"session_id": "s-1"}),
            _ev(2, ChatEventType.CHAT_FAILED, {
                "code": "CHAT_EXEC_FAILED", "message": "boom",
            }),
        ]
        app, cache = _make_app(use_case=_make_uc_yielding(events))
        client = TestClient(app)

        with client.websocket_connect("/ws/chat/s-1?token=t") as ws:
            ws.send_json({"type": "subscribe", "message": "x"})
            _ = ws.receive_json()
            failed = ws.receive_json()
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

        assert failed["type"] == "chat_failed"
        assert failed["data"]["code"] == "CHAT_EXEC_FAILED"
        assert cache.clear_calls == ["s-1"]

    def test_use_case_exception_yields_internal_error(self) -> None:
        app, _ = _make_app(use_case=_make_uc_raising(RuntimeError("kaboom")))
        client = TestClient(app)
        with client.websocket_connect("/ws/chat/s-1?token=t") as ws:
            ws.send_json({"type": "subscribe", "message": "x"})
            err = ws.receive_json()
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
        assert err["type"] == "error"
        assert err["data"]["code"] == "INTERNAL_ERROR"
        assert exc.value.code == WSCloseCode.INTERNAL_ERROR
