"""WebSocket router — echo endpoint + DI placeholders."""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.domain.auth.interfaces import JWTAdapterInterface, UserRepositoryInterface
from src.domain.websocket.interfaces import ConnectionManagerInterface
from src.domain.websocket.schemas import WSMessage
from src.infrastructure.websocket.auth import verify_ws_token

router = APIRouter(tags=["websocket"])


def get_connection_manager() -> ConnectionManagerInterface:
    raise NotImplementedError("ConnectionManager not initialized")


def get_ws_jwt_adapter() -> JWTAdapterInterface:
    raise NotImplementedError("JWTAdapter not initialized")


def get_ws_user_repository() -> UserRepositoryInterface:
    raise NotImplementedError("UserRepository not initialized")


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
