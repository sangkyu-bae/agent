"""WebSocket token authentication helper."""
from typing import Optional

from fastapi import WebSocket

from src.domain.auth.entities import User
from src.domain.auth.interfaces import JWTAdapterInterface, UserRepositoryInterface
from src.domain.websocket.schemas import WSCloseCode


async def verify_ws_token(
    websocket: WebSocket,
    jwt_adapter: JWTAdapterInterface,
    user_repo: UserRepositoryInterface,
) -> Optional[User]:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=WSCloseCode.AUTH_FAILED, reason="Token required")
        return None

    try:
        payload = jwt_adapter.decode(token)
    except ValueError:
        await websocket.close(
            code=WSCloseCode.AUTH_FAILED, reason="Invalid or expired token"
        )
        return None

    if payload.token_type != "access":
        await websocket.close(
            code=WSCloseCode.AUTH_FAILED, reason="Invalid token type"
        )
        return None

    user = await user_repo.find_by_id(int(payload.sub))
    if not user:
        await websocket.close(code=WSCloseCode.AUTH_FAILED, reason="User not found")
        return None

    return user
