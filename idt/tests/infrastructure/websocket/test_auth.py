"""Tests for WS token authentication (TDD: written before implementation)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.auth.value_objects import TokenPayload
from src.domain.websocket.schemas import WSCloseCode
from src.infrastructure.websocket.auth import verify_ws_token


def _make_ws(token: str | None = "valid-jwt") -> AsyncMock:
    ws = AsyncMock()
    ws.close = AsyncMock()
    ws.query_params = {"token": token} if token else {}
    return ws


def _make_jwt_adapter(
    payload: TokenPayload | None = None, raise_error: bool = False
) -> MagicMock:
    adapter = MagicMock()
    if raise_error:
        adapter.decode.side_effect = ValueError("Invalid token")
    elif payload:
        adapter.decode.return_value = payload
    else:
        adapter.decode.return_value = TokenPayload(
            sub="1", role="user", token_type="access", exp=9999999999
        )
    return adapter


def _make_user_repo(user: User | None = None) -> AsyncMock:
    repo = AsyncMock()
    if user is None:
        user = User(
            id=1,
            email="test@test.com",
            password_hash="hash",
            role=UserRole.USER,
            status=UserStatus.APPROVED,
        )
    repo.find_by_id = AsyncMock(return_value=user)
    return repo


class TestVerifyWsToken:
    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self) -> None:
        ws = _make_ws("valid-jwt")
        jwt = _make_jwt_adapter()
        repo = _make_user_repo()

        user = await verify_ws_token(ws, jwt, repo)
        assert user is not None
        assert user.id == 1
        ws.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_token_closes_4001(self) -> None:
        ws = _make_ws(token=None)
        jwt = _make_jwt_adapter()
        repo = _make_user_repo()

        result = await verify_ws_token(ws, jwt, repo)
        assert result is None
        ws.close.assert_awaited_once()
        assert ws.close.call_args.kwargs.get("code") == WSCloseCode.AUTH_FAILED

    @pytest.mark.asyncio
    async def test_invalid_token_closes_4001(self) -> None:
        ws = _make_ws("bad-token")
        jwt = _make_jwt_adapter(raise_error=True)
        repo = _make_user_repo()

        result = await verify_ws_token(ws, jwt, repo)
        assert result is None
        ws.close.assert_awaited_once()
        assert ws.close.call_args.kwargs.get("code") == WSCloseCode.AUTH_FAILED

    @pytest.mark.asyncio
    async def test_refresh_token_rejected(self) -> None:
        ws = _make_ws("refresh-jwt")
        payload = TokenPayload(sub="1", role="user", token_type="refresh", exp=9999999999)
        jwt = _make_jwt_adapter(payload=payload)
        repo = _make_user_repo()

        result = await verify_ws_token(ws, jwt, repo)
        assert result is None
        ws.close.assert_awaited_once()
        assert ws.close.call_args.kwargs.get("code") == WSCloseCode.AUTH_FAILED

    @pytest.mark.asyncio
    async def test_user_not_found_closes_4001(self) -> None:
        ws = _make_ws("valid-jwt")
        jwt = _make_jwt_adapter()
        repo = AsyncMock()
        repo.find_by_id = AsyncMock(return_value=None)

        result = await verify_ws_token(ws, jwt, repo)
        assert result is None
        ws.close.assert_awaited_once()
        assert ws.close.call_args.kwargs.get("code") == WSCloseCode.AUTH_FAILED
