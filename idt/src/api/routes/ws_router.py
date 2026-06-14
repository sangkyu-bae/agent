"""WebSocket router — echo + agent run + general chat streaming endpoints.

Endpoints:
- `/ws/echo` — 인증 + echo (인프라 동작 검증용)
- `/ws/agent/{run_id}` — Agent 실행 실시간 스트리밍
  (Design fe-websocket-integration-guide §4.1)
- `/ws/chat/{session_id}` — General Chat 실시간 토큰 스트리밍
  (Design ws-chat-streaming §4.3, with replay cache)

DI placeholder는 lifespan에서 override (main.py).
"""
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from src.application.agent_attachment.resolver import AttachmentResolver
from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import RunAgentRequest
from src.application.agent_run.ws_auth_context import WsAuthContextResolver
from src.application.general_chat.use_case import GeneralChatUseCase
from src.api.routes.ws_schemas import SubscribeAgentRunPayload, SubscribeChatPayload
from src.domain.agent_attachment.exceptions import (
    AttachmentAccessDeniedError,
    AttachmentNotFoundError,
)
from src.domain.agent_run.auth_context import AuthContext
from src.domain.auth.entities import User
from src.domain.auth.interfaces import JWTAdapterInterface, UserRepositoryInterface
from src.domain.general_chat.interfaces import ChatStreamCacheInterface
from src.domain.general_chat.schemas import GeneralChatRequest
from src.domain.general_chat.value_objects import ChatEventType
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.websocket.interfaces import ConnectionManagerInterface
from src.domain.websocket.schemas import WSCloseCode, WSMessage
from src.infrastructure.agent_run.ws_adapter import AgentRunEventWsAdapter
from src.infrastructure.general_chat.ws_adapter import ChatEventWsAdapter
from src.infrastructure.websocket.auth import verify_ws_token

router = APIRouter(tags=["websocket"])


def get_connection_manager() -> ConnectionManagerInterface:
    raise NotImplementedError("ConnectionManager not initialized")


def get_ws_jwt_adapter() -> JWTAdapterInterface:
    raise NotImplementedError("JWTAdapter not initialized")


def get_ws_user_repository() -> UserRepositoryInterface:
    raise NotImplementedError("UserRepository not initialized")


def get_ws_run_agent_use_case() -> RunAgentUseCase:
    raise NotImplementedError("RunAgentUseCase not initialized")


def get_ws_general_chat_use_case() -> GeneralChatUseCase:
    raise NotImplementedError("GeneralChatUseCase not initialized")


def get_chat_stream_cache() -> ChatStreamCacheInterface:
    raise NotImplementedError("ChatStreamCache not initialized")


def get_ws_auth_context_resolver() -> WsAuthContextResolver:
    raise NotImplementedError("WsAuthContextResolver not initialized")


def get_ws_attachment_resolver() -> AttachmentResolver:
    raise NotImplementedError("AttachmentResolver not initialized")


def get_ws_logger() -> LoggerInterface:
    raise NotImplementedError("WS logger not initialized")


async def _resolve_ws_auth_ctx(
    user: User,
    resolver: WsAuthContextResolver,
    logger: LoggerInterface,
) -> AuthContext:
    """User → AuthContext 조립. 실패 시 anonymous로 degrade (fail-closed).

    fix-ws-auth-context-missing Design §3.2.2: 조립 실패가 채팅 자체를 막지 않도록
    anonymous AuthContext로 진행한다 (사용자 블록 미노출 + 권한 Tool 자동 거부).
    """
    request_id = str(uuid.uuid4())
    try:
        return await resolver.execute(user, request_id)
    except Exception as e:
        logger.error(
            "WS AuthContext assembly failed — degrading to anonymous",
            exception=e, request_id=request_id,
        )
        return AuthContext.public_anonymous()


class _AttachmentResolveError(Exception):
    """첨부 해석 실패 — code/message를 담아 라우터가 close 처리한다."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _resolve_ws_attachments(
    sub: SubscribeAgentRunPayload,
    resolver: AttachmentResolver,
    viewer_user_id: str,
) -> tuple[list[dict] | None, list[str]]:
    """subscribe.attachments → (RunAgentRequest용 attachment dict, cleanup용 file_id 목록).

    ws-agent-excel-attachment Design §4.3. 없으면 (None, []).
    Raises:
        _AttachmentResolveError: not_found / access_denied
    """
    if not sub.attachments:
        return None, []
    refs = [{"type": a.type, "file_id": a.file_id} for a in sub.attachments]
    try:
        resolved = resolver.resolve_many(refs, viewer_user_id=viewer_user_id)
    except AttachmentNotFoundError as e:
        raise _AttachmentResolveError(
            "ATTACHMENT_NOT_FOUND", f"첨부를 찾을 수 없습니다: {e}"
        )
    except AttachmentAccessDeniedError as e:
        raise _AttachmentResolveError(
            "ATTACHMENT_ACCESS_DENIED", f"첨부 접근 권한이 없습니다: {e}"
        )
    return resolved, [a.file_id for a in sub.attachments]


async def _reject_subscribe(
    manager: ConnectionManagerInterface,
    websocket: WebSocket,
    user_id: int,
    run_id: str,
    code: str,
    message: str,
) -> None:
    """subscribe 검증 실패 시 error 전송 + disconnect + close(4002)."""
    err = WSMessage(type="error", data={"code": code, "message": message})
    await manager.send_personal(websocket, err.model_dump(mode="json"))
    await manager.disconnect(websocket, user_id, room_id=run_id)
    await websocket.close(code=WSCloseCode.FORBIDDEN)


@router.websocket("/ws/echo")
async def ws_echo(
    websocket: WebSocket,
    manager: ConnectionManagerInterface = Depends(get_connection_manager),
    jwt_adapter: JWTAdapterInterface = Depends(get_ws_jwt_adapter),
    user_repo: UserRepositoryInterface = Depends(get_ws_user_repository),
):
    user = await verify_ws_token(websocket, jwt_adapter, user_repo)
    if not user:
        return

    await manager.connect(websocket, user.id)
    try:
        connected_msg = WSMessage(
            type="connected",
            data={"user_id": user.id, "message": "WebSocket connected"},
        )
        await manager.send_personal(websocket, connected_msg.model_dump(mode="json"))

        while True:
            raw = await websocket.receive_json()
            echo_msg = WSMessage(type="echo", data={"original": raw})
            await manager.send_personal(
                websocket, echo_msg.model_dump(mode="json")
            )

    except WebSocketDisconnect:
        await manager.disconnect(websocket, user.id)
    except Exception as e:
        error_msg = WSMessage(
            type="error",
            data={"code": "INTERNAL_ERROR", "message": str(e)},
        )
        try:
            await manager.send_personal(
                websocket, error_msg.model_dump(mode="json")
            )
        except Exception:
            pass
        await manager.disconnect(websocket, user.id)


@router.websocket("/ws/agent/{run_id}")
async def ws_agent_run(
    websocket: WebSocket,
    run_id: str,
    manager: ConnectionManagerInterface = Depends(get_connection_manager),
    jwt_adapter: JWTAdapterInterface = Depends(get_ws_jwt_adapter),
    user_repo: UserRepositoryInterface = Depends(get_ws_user_repository),
    use_case: RunAgentUseCase = Depends(get_ws_run_agent_use_case),
    auth_resolver: WsAuthContextResolver = Depends(get_ws_auth_context_resolver),
    attachment_resolver: AttachmentResolver = Depends(get_ws_attachment_resolver),
    logger: LoggerInterface = Depends(get_ws_logger),
):
    """Agent 실행 실시간 스트리밍.

    Wire protocol:
        C → S (첫 메시지):
            { type: "subscribe", agent_id, query, session_id?,
              attachments?: [{type:"excel", file_id}] }
        S → C: AgentRunEventWsAdapter.to_ws_message(event)  (loop)
        S closes(1000) on RUN_COMPLETED, closes(4500) on internal error.

    ws-agent-excel-attachment: attachments는 업로드된 file_id 참조이며,
    소유자 검증 후 file_path로 해석되어 분석 노드에 전달된다.
    run 종료(정상/예외/disconnect) 시 임시 파일을 finally에서 자동 삭제한다.
    """
    user = await verify_ws_token(websocket, jwt_adapter, user_repo)
    if not user:
        return
    auth_ctx = await _resolve_ws_auth_ctx(user, auth_resolver, logger)

    await manager.connect(websocket, user.id, room_id=run_id)
    attachment_file_ids: list[str] = []
    try:
        raw_first = await websocket.receive_json()
        try:
            sub = SubscribeAgentRunPayload.model_validate(raw_first)
        except ValidationError as ve:
            await _reject_subscribe(
                manager, websocket, user.id, run_id,
                "INVALID_SUBSCRIBE", str(ve)[:512],
            )
            return

        try:
            attachments, attachment_file_ids = _resolve_ws_attachments(
                sub, attachment_resolver, str(user.id),
            )
        except _AttachmentResolveError as ae:
            await _reject_subscribe(
                manager, websocket, user.id, run_id, ae.code, ae.message,
            )
            return

        request = RunAgentRequest(
            user_id=str(user.id),
            query=sub.query,
            session_id=sub.session_id,
            attachments=attachments,
        )

        async for event in use_case.stream(
            agent_id=sub.agent_id,
            request=request,
            request_id=run_id,
            viewer_user_id=str(user.id),
            viewer_department_ids=list(auth_ctx.department_ids),
            auth_ctx=auth_ctx,
        ):
            ws_msg = AgentRunEventWsAdapter.to_ws_message(event)
            await manager.send_to_room(
                run_id, ws_msg.model_dump(mode="json")
            )

        await manager.disconnect(websocket, user.id, room_id=run_id)
        await websocket.close(code=WSCloseCode.NORMAL)

    except WebSocketDisconnect:
        await manager.disconnect(websocket, user.id, room_id=run_id)
    except Exception as e:
        err = WSMessage(
            type="error",
            data={"code": "INTERNAL_ERROR", "message": str(e)[:512]},
        )
        try:
            await manager.send_personal(websocket, err.model_dump(mode="json"))
        except Exception:
            pass
        await manager.disconnect(websocket, user.id, room_id=run_id)
        try:
            await websocket.close(code=WSCloseCode.INTERNAL_ERROR)
        except Exception:
            pass
    finally:
        # ws-agent-excel-attachment Design §4.3: run 종료 시 임시 파일 자동 삭제.
        if attachment_file_ids:
            attachment_resolver.cleanup(attachment_file_ids)


@router.websocket("/ws/chat/{session_id}")
async def ws_chat(
    websocket: WebSocket,
    session_id: str,
    manager: ConnectionManagerInterface = Depends(get_connection_manager),
    jwt_adapter: JWTAdapterInterface = Depends(get_ws_jwt_adapter),
    user_repo: UserRepositoryInterface = Depends(get_ws_user_repository),
    use_case: GeneralChatUseCase = Depends(get_ws_general_chat_use_case),
    cache: ChatStreamCacheInterface = Depends(get_chat_stream_cache),
    auth_resolver: WsAuthContextResolver = Depends(get_ws_auth_context_resolver),
    logger: LoggerInterface = Depends(get_ws_logger),
):
    """General Chat 실시간 토큰 스트리밍.

    Wire protocol:
        S → C (replay, optional): cached chat events (metadata.cached=True)
        C → S (첫 메시지): { type: "subscribe", message, top_k?, llm_model_id? }
        S → C: ChatEventWsAdapter.to_ws_message(event)  (loop)
        S closes(1000) on CHAT_DONE, closes(4500) on internal error.

    Plan Q3: 새 탭/재접속 시 진행 중 stream events를 cache에서 replay.
    """
    user = await verify_ws_token(websocket, jwt_adapter, user_repo)
    if not user:
        return
    auth_ctx = await _resolve_ws_auth_ctx(user, auth_resolver, logger)

    await manager.connect(websocket, user.id, room_id=session_id)
    try:
        # Q3: replay 진행 중인 stream events (있다면)
        for ev in await cache.replay(session_id):
            msg = ChatEventWsAdapter.to_ws_message(ev, cached=True)
            await manager.send_personal(websocket, msg.model_dump(mode="json"))

        raw_first = await websocket.receive_json()
        try:
            sub = SubscribeChatPayload.model_validate(raw_first)
        except ValidationError as ve:
            err = WSMessage(
                type="error",
                data={"code": "INVALID_SUBSCRIBE", "message": str(ve)[:512]},
            )
            await manager.send_personal(websocket, err.model_dump(mode="json"))
            await manager.disconnect(websocket, user.id, room_id=session_id)
            await websocket.close(code=WSCloseCode.FORBIDDEN)
            return

        request = GeneralChatRequest(
            user_id=str(user.id),
            session_id=session_id,
            message=sub.message,
            top_k=sub.top_k or 5,
        )

        async for event in use_case.stream(
            request, request_id=session_id, auth_ctx=auth_ctx,
        ):
            ws_msg = ChatEventWsAdapter.to_ws_message(event)
            await cache.record(session_id, event)  # Q3 replay 누적
            await manager.send_to_room(
                session_id, ws_msg.model_dump(mode="json"),
            )
            if event.event_type in (
                ChatEventType.CHAT_DONE, ChatEventType.CHAT_FAILED,
            ):
                await cache.clear(session_id)  # 명시적 정리 (TTL 백업)

        await manager.disconnect(websocket, user.id, room_id=session_id)
        await websocket.close(code=WSCloseCode.NORMAL)

    except WebSocketDisconnect:
        await manager.disconnect(websocket, user.id, room_id=session_id)
    except Exception as e:
        err = WSMessage(
            type="error",
            data={"code": "INTERNAL_ERROR", "message": str(e)[:512]},
        )
        try:
            await manager.send_personal(websocket, err.model_dump(mode="json"))
        except Exception:
            pass
        await manager.disconnect(websocket, user.id, room_id=session_id)
        try:
            await websocket.close(code=WSCloseCode.INTERNAL_ERROR)
        except Exception:
            pass
