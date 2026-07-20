"""API 테스트: MemoryRouter (agent-memory Design §3-4).

결정 ②: 401 미인증 / 404 타인·미존재 은닉 / 422 검증(타입·길이·상한).
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.memory_router import router, get_memory_crud_use_case
from src.domain.agent_run.auth_context import AuthContext
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.memory.entity import Memory, MemoryScope, MemoryStatus, MemoryType
from src.interfaces.dependencies.auth import get_auth_context, get_current_user

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


def _org_memory(memory_id=20, content="부서 용어") -> Memory:
    return Memory(
        id=memory_id, scope=MemoryScope.ORG, user_id="d1", tier=0,
        mem_type=MemoryType.DOMAIN_TERM, content=content,
        status=MemoryStatus.ACTIVE, created_at=NOW, updated_at=NOW,
    )


def _ctx(role="user", dept_ids=("d1",)) -> AuthContext:
    return AuthContext(
        user_id=7, display_name="배상규", role=role,
        primary_department_id=dept_ids[0] if dept_ids else None,
        primary_department_name="여신심사팀",
        department_ids=tuple(dept_ids), department_names=("여신심사팀",),
        permissions=frozenset(),
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
    uc.max_pending_per_user = 20
    uc.list_active = AsyncMock(return_value=[_memory(1), _memory(2, "둘째")])
    uc.list_by_status = AsyncMock(return_value=[_memory(9, "승인 대기 후보")])
    uc.create = AsyncMock(return_value=_memory(3))
    uc.update = AsyncMock(return_value=_memory(1, "수정됨"))
    uc.delete = AsyncMock(return_value=None)
    uc.approve = AsyncMock(return_value=_memory(9, "승인됨"))
    uc.reject = AsyncMock(return_value=_memory(9, "거부됨"))
    uc.max_active_per_department = 50
    uc.list_org = AsyncMock(return_value=[_org_memory(20)])
    uc.create_org = AsyncMock(return_value=_org_memory(21))
    uc.promote = AsyncMock(return_value=_org_memory(22))
    return uc


@pytest.fixture
def client(app, crud_uc):
    app.dependency_overrides[get_memory_crud_use_case] = lambda: crud_uc
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_auth_context] = lambda: _ctx()
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


class TestListByStatus:
    def test_pending_조회는_pending_상한을_max_count로(self, client, crud_uc):
        r = client.get("/api/v1/memories?status=pending")

        assert r.status_code == 200
        body = r.json()
        assert body["max_count"] == 20
        assert body["items"][0]["content"] == "승인 대기 후보"
        crud_uc.list_by_status.assert_awaited_once()

    def test_status_active는_기존_경로(self, client, crud_uc):
        r = client.get("/api/v1/memories?status=active")
        assert r.status_code == 200
        assert r.json()["max_count"] == 30
        crud_uc.list_active.assert_awaited_once()

    def test_불량_status는_422(self, client):
        assert client.get("/api/v1/memories?status=weird").status_code == 422


class TestApproveReject:
    def test_승인은_200(self, client, crud_uc):
        r = client.patch("/api/v1/memories/9/approve")

        assert r.status_code == 200
        assert crud_uc.approve.await_args.args[:2] == ("7", 9)

    def test_거부는_200(self, client, crud_uc):
        r = client.patch("/api/v1/memories/9/reject")

        assert r.status_code == 200
        assert crud_uc.reject.await_args.args[:2] == ("7", 9)

    def test_비pending_승인은_422(self, app, crud_uc):
        crud_uc.approve = AsyncMock(
            side_effect=ValueError("승인 대기 상태의 메모리만 승인/거부할 수 있습니다.")
        )
        app.dependency_overrides[get_memory_crud_use_case] = lambda: crud_uc
        app.dependency_overrides[get_current_user] = _user
        c = TestClient(app)

        assert c.patch("/api/v1/memories/1/approve").status_code == 422

    def test_타인_미존재_승인은_404_은닉(self, app, crud_uc):
        crud_uc.approve = AsyncMock(side_effect=ValueError("메모리를 찾을 수 없습니다."))
        app.dependency_overrides[get_memory_crud_use_case] = lambda: crud_uc
        app.dependency_overrides[get_current_user] = _user
        c = TestClient(app)

        assert c.patch("/api/v1/memories/99/approve").status_code == 404


class TestOrgScope:
    def test_부서_메모리_목록은_dept_상한을_max_count로(self, client):
        r = client.get("/api/v1/memories/org")

        assert r.status_code == 200
        body = r.json()
        assert body["max_count"] == 50
        assert body["items"][0]["content"] == "부서 용어"

    def test_부서_메모리_작성은_201(self, client, crud_uc):
        r = client.post(
            "/api/v1/memories/org",
            json={"dept_id": "d1", "mem_type": "domain_term", "content": "부서 용어"},
        )

        assert r.status_code == 201
        assert crud_uc.create_org.await_args.args[0] == "d1"

    def test_소속외_부서_작성은_403(self, app, crud_uc):
        app.dependency_overrides[get_memory_crud_use_case] = lambda: crud_uc
        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_auth_context] = lambda: _ctx(dept_ids=("d1",))
        c = TestClient(app)

        r = c.post(
            "/api/v1/memories/org",
            json={"dept_id": "d9", "mem_type": "domain_term", "content": "x"},
        )

        assert r.status_code == 403

    def test_admin은_타부서도_작성_가능(self, app, crud_uc):
        app.dependency_overrides[get_memory_crud_use_case] = lambda: crud_uc
        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_auth_context] = lambda: _ctx(role="admin", dept_ids=())
        c = TestClient(app)

        r = c.post(
            "/api/v1/memories/org",
            json={"dept_id": "d9", "mem_type": "domain_term", "content": "x"},
        )

        assert r.status_code == 201

    def test_승격은_201(self, client, crud_uc):
        r = client.post("/api/v1/memories/5/promote", json={"dept_id": "d1"})

        assert r.status_code == 201
        assert crud_uc.promote.await_args.args[:3] == ("7", 5, "d1")

    def test_승격_중복은_409(self, app, crud_uc):
        crud_uc.promote = AsyncMock(side_effect=ValueError("이미 부서에 등록된 내용입니다."))
        app.dependency_overrides[get_memory_crud_use_case] = lambda: crud_uc
        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_auth_context] = lambda: _ctx()
        c = TestClient(app)

        r = c.post("/api/v1/memories/5/promote", json={"dept_id": "d1"})

        assert r.status_code == 409


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
