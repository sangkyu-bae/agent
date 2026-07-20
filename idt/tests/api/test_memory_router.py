"""API 테스트: MemoryRouter (agent-memory Design §3-4).

결정 ②: 401 미인증 / 404 타인·미존재 은닉 / 422 검증(타입·길이·상한).
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.memory_router import router, get_memory_crud_use_case
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.memory.entity import Memory, MemoryScope, MemoryStatus, MemoryType
from src.interfaces.dependencies.auth import get_current_user

NOW = datetime(2026, 7, 18, 12, 0, 0)


def _user() -> User:
    return User(
        email="user@example.com", password_hash="hashed",
        role=UserRole.USER, status=UserStatus.APPROVED, id=7,
    )


def _memory(memory_id=1, content="여신 심사팀 소속") -> Memory:
    return Memory(
        id=memory_id, scope=MemoryScope.USER, user_id="7", tier=0,
        mem_type=MemoryType.PROFILE, content=content,
        status=MemoryStatus.ACTIVE, created_at=NOW, updated_at=NOW,
    )


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def crud_uc():
    uc = MagicMock()
    uc.max_active_per_user = 30
    uc.list_active = AsyncMock(return_value=[_memory(1), _memory(2, "둘째")])
    uc.create = AsyncMock(return_value=_memory(3))
    uc.update = AsyncMock(return_value=_memory(1, "수정됨"))
    uc.delete = AsyncMock(return_value=None)
    return uc


@pytest.fixture
def client(app, crud_uc):
    app.dependency_overrides[get_memory_crud_use_case] = lambda: crud_uc
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app)


class TestAuth:
    def test_미인증은_401(self, app, crud_uc):
        app.dependency_overrides[get_memory_crud_use_case] = lambda: crud_uc
        c = TestClient(app)
        assert c.get("/api/v1/memories").status_code == 401


class TestList:
    def test_목록은_total과_max_count_포함(self, client, crud_uc):
        r = client.get("/api/v1/memories")

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        assert body["max_count"] == 30
        assert body["items"][0]["mem_type"] == "profile"
        assert body["items"][0]["content"] == "여신 심사팀 소속"
        # 인증 사용자 id의 str 변환이 그대로 전달된다 (agent_builder 선례)
        crud_uc.list_active.assert_awaited_once()
        assert crud_uc.list_active.await_args.args[0] == "7"


class TestCreate:
    def test_생성은_201(self, client, crud_uc):
        r = client.post(
            "/api/v1/memories",
            json={"mem_type": "profile", "content": "여신 심사팀 소속"},
        )

        assert r.status_code == 201
        assert r.json()["id"] == 3
        assert crud_uc.create.await_args.args[0] == "7"

    def test_상한_초과는_422(self, app, crud_uc):
        crud_uc.create = AsyncMock(side_effect=ValueError("메모리 개수 상한(30개)에 도달했습니다."))
        app.dependency_overrides[get_memory_crud_use_case] = lambda: crud_uc
        app.dependency_overrides[get_current_user] = _user
        c = TestClient(app)

        r = c.post("/api/v1/memories", json={"mem_type": "profile", "content": "x"})

        assert r.status_code == 422
        assert "상한" in r.json()["detail"]

    def test_본문_누락은_422(self, client):
        assert client.post("/api/v1/memories", json={"mem_type": "profile"}).status_code == 422


class TestUpdate:
    def test_수정은_200(self, client, crud_uc):
        r = client.patch("/api/v1/memories/1", json={"content": "수정됨"})

        assert r.status_code == 200
        assert r.json()["content"] == "수정됨"

    def test_타인_미존재는_404_은닉(self, app, crud_uc):
        crud_uc.update = AsyncMock(side_effect=ValueError("메모리를 찾을 수 없습니다."))
        app.dependency_overrides[get_memory_crud_use_case] = lambda: crud_uc
        app.dependency_overrides[get_current_user] = _user
        c = TestClient(app)

        assert c.patch("/api/v1/memories/99", json={"content": "x"}).status_code == 404


class TestDelete:
    def test_삭제는_204(self, client, crud_uc):
        r = client.delete("/api/v1/memories/1")

        assert r.status_code == 204
        assert crud_uc.delete.await_args.args[:2] == ("7", 1)

    def test_타인_미존재는_404_은닉(self, app, crud_uc):
        crud_uc.delete = AsyncMock(side_effect=ValueError("메모리를 찾을 수 없습니다."))
        app.dependency_overrides[get_memory_crud_use_case] = lambda: crud_uc
        app.dependency_overrides[get_current_user] = _user
        c = TestClient(app)

        assert c.delete("/api/v1/memories/99").status_code == 404
