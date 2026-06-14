"""WS /ws/agent/{run_id} 엔드포인트 통합 테스트.

Design fe-websocket-integration-guide §4.1.
TestClient.websocket_connect()로 wire-level 동작 검증.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

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
    get_ws_auth_context_resolver,
    get_ws_attachment_resolver,
    get_ws_logger,
)
from src.domain.agent_run.auth_context import AuthContext
from src.domain.agent_run.value_objects import (
    AgentRunEvent,
    AgentRunEventType,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.auth.value_objects import TokenPayload
from src.domain.websocket.schemas import WSCloseCode
from src.infrastructure.websocket.connection_manager import ConnectionManager


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
        timestamp=datetime(2026, 5, 25, tzinfo=timezone.utc),
    )


def _make_uc_yielding(events: list[AgentRunEvent]):
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
    adapter = MagicMock()
    adapter.decode.return_value = TokenPayload(
        sub=user_id, role="user", token_type=token_type, exp=9999999999
    )
    return adapter


def _make_user_repo(user: User | None = None) -> MagicMock:
    from unittest.mock import AsyncMock
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=user if user is not None else _fake_user())
    return repo


def _make_auth_resolver() -> MagicMock:
    """기본 AuthContext를 반환하는 fake resolver (auth_ctx 전달 후 테스트는 별도 파일)."""
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


def _make_attachment_resolver() -> MagicMock:
    """기본: 첨부 없음 가정 (resolve_many 호출되지 않음). cleanup은 no-op."""
    resolver = MagicMock()
    resolver.resolve_many = MagicMock(return_value=[])
    resolver.cleanup = MagicMock()
    return resolver


def _make_app(
    use_case,
    user: User | None = None,
    jwt_adapter: MagicMock | None = None,
    attachment_resolver: MagicMock | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    manager = ConnectionManager(logger=logger)

    resolver = attachment_resolver or _make_attachment_resolver()

    app.dependency_overrides[get_connection_manager] = lambda: manager
    app.dependency_overrides[get_ws_jwt_adapter] = (
        lambda: jwt_adapter if jwt_adapter is not None else _make_jwt_adapter()
    )
    app.dependency_overrides[get_ws_user_repository] = (
        lambda: _make_user_repo(user)
    )
    app.dependency_overrides[get_ws_run_agent_use_case] = lambda: use_case
    app.dependency_overrides[get_ws_auth_context_resolver] = _make_auth_resolver
    app.dependency_overrides[get_ws_attachment_resolver] = lambda: resolver
    app.dependency_overrides[get_ws_logger] = lambda: logger
    return app


class TestAuth:
    def test_no_token_closes_4001(self) -> None:
        app = _make_app(use_case=_make_uc_yielding([]))
        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/agent/run-1") as ws:
                ws.receive_json()
        assert exc.value.code == WSCloseCode.AUTH_FAILED

    def test_refresh_token_rejected(self) -> None:
        app = _make_app(
            use_case=_make_uc_yielding([]),
            jwt_adapter=_make_jwt_adapter(token_type="refresh"),
        )
        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/agent/run-1?token=t") as ws:
                ws.receive_json()
        assert exc.value.code == WSCloseCode.AUTH_FAILED


class TestSubscribeValidation:
    def test_invalid_subscribe_payload_rejected(self) -> None:
        app = _make_app(use_case=_make_uc_yielding([]))
        client = TestClient(app)
        with client.websocket_connect("/ws/agent/run-1?token=t") as ws:
            ws.send_json({"type": "wrong", "agent_id": "a", "query": "q"})
            err = ws.receive_json()
            assert err["type"] == "error"
            assert err["data"]["code"] == "INVALID_SUBSCRIBE"
            # 서버가 close → 다음 recv는 disconnect
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()


class TestHappyPath:
    def test_stream_yields_mapped_messages_in_order(self) -> None:
        events = [
            _ev(1, AgentRunEventType.RUN_STARTED,
                {"run_id": "rid", "session_id": "s", "agent_id": "a"}),
            _ev(2, AgentRunEventType.TOKEN,
                {"chunk": "안녕", "node_name": "final_answer"}),
            _ev(3, AgentRunEventType.ANSWER_COMPLETED,
                {"answer": "안녕하세요", "tools_used": []}),
            _ev(4, AgentRunEventType.RUN_COMPLETED,
                {"run_id": "rid", "langsmith_run_url": None}),
        ]
        app = _make_app(use_case=_make_uc_yielding(events))
        client = TestClient(app)

        with client.websocket_connect("/ws/agent/rid?token=t") as ws:
            ws.send_json({
                "type": "subscribe",
                "agent_id": "a",
                "query": "hi",
            })
            msgs = [ws.receive_json() for _ in range(4)]
            # 서버가 정상 close → 다음 recv는 disconnect 1000
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()

        types = [m["type"] for m in msgs]
        assert types == [
            "agent_run_started",
            "agent_token",
            "agent_answer_completed",
            "agent_run_completed",
        ]
        assert msgs[1]["data"]["chunk"] == "안녕"
        assert msgs[1]["metadata"]["seq"] == 2
        assert exc.value.code == WSCloseCode.NORMAL


class TestErrorPath:
    def test_run_failed_event_propagated(self) -> None:
        events = [
            _ev(1, AgentRunEventType.RUN_STARTED,
                {"run_id": "rid", "session_id": "s", "agent_id": "a"}),
            _ev(2, AgentRunEventType.RUN_FAILED,
                {"code": "GRAPH_EXEC_FAILED", "message": "boom"}),
        ]
        app = _make_app(use_case=_make_uc_yielding(events))
        client = TestClient(app)

        with client.websocket_connect("/ws/agent/rid?token=t") as ws:
            ws.send_json({"type": "subscribe", "agent_id": "a", "query": "q"})
            _ = ws.receive_json()  # run_started
            failed = ws.receive_json()
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

        assert failed["type"] == "agent_run_failed"
        assert failed["data"]["code"] == "GRAPH_EXEC_FAILED"

    def test_use_case_exception_yields_internal_error(self) -> None:
        app = _make_app(use_case=_make_uc_raising(RuntimeError("kaboom")))
        client = TestClient(app)

        with client.websocket_connect("/ws/agent/rid?token=t") as ws:
            ws.send_json({"type": "subscribe", "agent_id": "a", "query": "q"})
            err = ws.receive_json()
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()

        assert err["type"] == "error"
        assert err["data"]["code"] == "INTERNAL_ERROR"
        assert "kaboom" in err["data"]["message"]
        assert exc.value.code == WSCloseCode.INTERNAL_ERROR


class TestAttachments:
    """ws-agent-excel-attachment: 첨부 전달 + cleanup 검증."""

    def _completed_events(self) -> list[AgentRunEvent]:
        return [
            _ev(1, AgentRunEventType.RUN_STARTED,
                {"run_id": "rid", "session_id": "s", "agent_id": "a"}),
            _ev(2, AgentRunEventType.RUN_COMPLETED,
                {"run_id": "rid", "langsmith_run_url": None}),
        ]

    def _capturing_uc(self, captured: dict):
        uc = MagicMock()

        def _stream(*args, **kwargs):
            captured["request"] = kwargs.get("request")

            async def _gen():
                for e in self._completed_events():
                    yield e
            return _gen()

        uc.stream = _stream
        return uc

    def test_attachments_forwarded_to_request(self) -> None:
        captured: dict = {}
        resolver = _make_attachment_resolver()
        resolver.resolve_many = MagicMock(return_value=[
            {"type": "excel", "file_path": "/tmp/x.xlsx", "user_id": "1"},
        ])
        app = _make_app(
            use_case=self._capturing_uc(captured),
            attachment_resolver=resolver,
        )
        client = TestClient(app)
        with client.websocket_connect("/ws/agent/rid?token=t") as ws:
            ws.send_json({
                "type": "subscribe", "agent_id": "a", "query": "분석",
                "attachments": [{"type": "excel", "file_id": "f" * 32}],
            })
            ws.receive_json()  # run_started
            ws.receive_json()  # run_completed
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

        # RunAgentRequest.attachments로 해석된 dict가 전달됨
        assert captured["request"].attachments == [
            {"type": "excel", "file_path": "/tmp/x.xlsx", "user_id": "1"}
        ]

    def test_cleanup_called_on_normal_completion(self) -> None:
        resolver = _make_attachment_resolver()
        resolver.resolve_many = MagicMock(return_value=[
            {"type": "excel", "file_path": "/tmp/x.xlsx", "user_id": "1"},
        ])
        app = _make_app(
            use_case=_make_uc_yielding(self._completed_events()),
            attachment_resolver=resolver,
        )
        client = TestClient(app)
        with client.websocket_connect("/ws/agent/rid?token=t") as ws:
            ws.send_json({
                "type": "subscribe", "agent_id": "a", "query": "q",
                "attachments": [{"type": "excel", "file_id": "f" * 32}],
            })
            ws.receive_json()  # run_started
            ws.receive_json()  # run_completed
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

        resolver.cleanup.assert_called_once_with(["f" * 32])

    def test_cleanup_called_on_stream_exception(self) -> None:
        resolver = _make_attachment_resolver()
        resolver.resolve_many = MagicMock(return_value=[
            {"type": "excel", "file_path": "/tmp/x.xlsx", "user_id": "1"},
        ])
        app = _make_app(
            use_case=_make_uc_raising(RuntimeError("boom")),
            attachment_resolver=resolver,
        )
        client = TestClient(app)
        with client.websocket_connect("/ws/agent/rid?token=t") as ws:
            ws.send_json({
                "type": "subscribe", "agent_id": "a", "query": "q",
                "attachments": [{"type": "excel", "file_id": "f" * 32}],
            })
            ws.receive_json()  # error
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

        # 예외 경로에서도 finally로 cleanup 보장
        resolver.cleanup.assert_called_once_with(["f" * 32])

    def test_not_found_closes_forbidden(self) -> None:
        from src.domain.agent_attachment.exceptions import AttachmentNotFoundError
        resolver = _make_attachment_resolver()
        resolver.resolve_many = MagicMock(side_effect=AttachmentNotFoundError("nope"))
        app = _make_app(
            use_case=_make_uc_yielding([]),
            attachment_resolver=resolver,
        )
        client = TestClient(app)
        with client.websocket_connect("/ws/agent/rid?token=t") as ws:
            ws.send_json({
                "type": "subscribe", "agent_id": "a", "query": "q",
                "attachments": [{"type": "excel", "file_id": "f" * 32}],
            })
            err = ws.receive_json()
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()

        assert err["data"]["code"] == "ATTACHMENT_NOT_FOUND"
        assert exc.value.code == WSCloseCode.FORBIDDEN
        # 해석 실패 시 cleanup 미호출 (소유 파일 보호)
        resolver.cleanup.assert_not_called()

    def test_no_attachments_keeps_legacy_behavior(self) -> None:
        """첨부 없는 기존 subscribe — resolve_many/cleanup 미호출 (회귀)."""
        resolver = _make_attachment_resolver()
        app = _make_app(
            use_case=_make_uc_yielding(self._completed_events()),
            attachment_resolver=resolver,
        )
        client = TestClient(app)
        with client.websocket_connect("/ws/agent/rid?token=t") as ws:
            ws.send_json({"type": "subscribe", "agent_id": "a", "query": "q"})
            ws.receive_json()  # run_started
            ws.receive_json()  # run_completed
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

        resolver.resolve_many.assert_not_called()
        resolver.cleanup.assert_not_called()
