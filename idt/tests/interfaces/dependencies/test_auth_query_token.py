"""get_current_user_from_query_token tests.

Design §5.4 (agent-run-streaming-sse). SSE/WebSocket 등 헤더 커스터마이즈 불가한
컨텍스트용 쿼리 파라미터 JWT 인증 dependency.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.auth.value_objects import TokenPayload
from src.interfaces.dependencies.auth import get_current_user_from_query_token


def _make_user() -> User:
    return User(
        id=42,
        email="user@example.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
    )


def _make_jwt_adapter(payload: TokenPayload | None, raises: Exception | None = None):
    adapter = MagicMock()
    if raises is not None:
        adapter.decode.side_effect = raises
    else:
        adapter.decode.return_value = payload
    return adapter


def _make_user_repo(user: User | None):
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=user)
    return repo


@pytest.mark.asyncio
async def test_valid_access_token_returns_user() -> None:
    user = _make_user()
    payload = TokenPayload(sub="42", role="user", token_type="access", exp=9999999999)
    jwt_adapter = _make_jwt_adapter(payload)
    user_repo = _make_user_repo(user)

    result = await get_current_user_from_query_token(
        token="valid.jwt.here",
        jwt_adapter=jwt_adapter,
        user_repo=user_repo,
    )

    assert result is user
    jwt_adapter.decode.assert_called_once_with("valid.jwt.here")
    user_repo.find_by_id.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_invalid_token_raises_401() -> None:
    jwt_adapter = _make_jwt_adapter(None, raises=ValueError("bad sig"))
    user_repo = _make_user_repo(None)

    with pytest.raises(HTTPException) as exc:
        await get_current_user_from_query_token(
            token="bogus",
            jwt_adapter=jwt_adapter,
            user_repo=user_repo,
        )
    assert exc.value.status_code == 401
    assert "Invalid" in exc.value.detail


@pytest.mark.asyncio
async def test_refresh_token_type_raises_401() -> None:
    payload = TokenPayload(sub="42", role="user", token_type="refresh", exp=9999999999)
    jwt_adapter = _make_jwt_adapter(payload)
    user_repo = _make_user_repo(_make_user())

    with pytest.raises(HTTPException) as exc:
        await get_current_user_from_query_token(
            token="refresh.token",
            jwt_adapter=jwt_adapter,
            user_repo=user_repo,
        )
    assert exc.value.status_code == 401
    assert "type" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_user_not_found_raises_401() -> None:
    payload = TokenPayload(sub="42", role="user", token_type="access", exp=9999999999)
    jwt_adapter = _make_jwt_adapter(payload)
    user_repo = _make_user_repo(None)

    with pytest.raises(HTTPException) as exc:
        await get_current_user_from_query_token(
            token="orphan",
            jwt_adapter=jwt_adapter,
            user_repo=user_repo,
        )
    assert exc.value.status_code == 401
    assert "User" in exc.value.detail
