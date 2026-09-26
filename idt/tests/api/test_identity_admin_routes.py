"""관리자 API — 메일함 PATCH, 회원 목록 mailbox_upn, MCP PUT null 전달.

Design Ref: mcp-identity-header §4.1, §4.2, §8.2 (#14~#16).
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.auth.list_users_use_case import UserListItem, UserListResult
from src.application.auth.update_user_mailbox_use_case import UserNotFoundError
from src.domain.auth.entities import User, UserRole, UserStatus


def _admin(role="admin") -> User:
    return User(email="admin@test.com", password_hash="h", role=UserRole(role),
                status=UserStatus.APPROVED, id=1)


def _client(overrides: dict, role: str = "admin") -> TestClient:
    from src.api.routes.admin_user_router import router
    from src.interfaces.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _admin(role)
    app.dependency_overrides.update(overrides)
    return TestClient(app)


def _mailbox_uc(result=None, error: Exception | None = None):
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=result, side_effect=error)
    return uc


class TestPatchMailbox:
    def _patch(self, uc, body, role="admin"):
        from src.api.routes.admin_user_router import get_update_user_mailbox_use_case
        client = _client({get_update_user_mailbox_use_case: lambda: uc}, role)
        return client.patch("/api/v1/admin/users/7/mailbox", json=body)

    def test_저장_결과를_돌려준다(self):
        user = User(id=7, email="kim@login.local", password_hash="h",
                    status=UserStatus.APPROVED, mailbox_upn="kim@corp.com")
        uc = _mailbox_uc(result=user)
        resp = self._patch(uc, {"mailbox_upn": "Kim@Corp.com"})
        assert resp.status_code == 200
        assert resp.json() == {
            "id": 7, "email": "kim@login.local", "mailbox_upn": "kim@corp.com"
        }
        assert uc.execute.call_args.args[:2] == (7, "Kim@Corp.com")

    def test_null은_해제로_전달된다(self):
        user = User(id=7, email="kim@login.local", password_hash="h")
        uc = _mailbox_uc(result=user)
        resp = self._patch(uc, {"mailbox_upn": None})
        assert resp.status_code == 200
        assert uc.execute.call_args.args[1] is None

    def test_형식_오류는_400(self):
        resp = self._patch(_mailbox_uc(error=ValueError("Mailbox must be an email address")),
                           {"mailbox_upn": "x"})
        assert resp.status_code == 400

    def test_긴_값도_도메인이_판정해_400(self):
        """Check G-5 — 스키마 max_length 로 422 가 섞이지 않는다."""
        uc = _mailbox_uc(error=ValueError("Mailbox must be at most 255 characters"))
        resp = self._patch(uc, {"mailbox_upn": "a" * 330 + "@corp.com"})
        assert resp.status_code == 400
        uc.execute.assert_awaited_once()

    def test_사용자_없음은_404(self):
        resp = self._patch(_mailbox_uc(error=UserNotFoundError(7)), {"mailbox_upn": "a@b.c"})
        assert resp.status_code == 404

    def test_관리자가_아니면_403(self):
        uc = _mailbox_uc()
        resp = self._patch(uc, {"mailbox_upn": "a@b.c"}, role="user")
        assert resp.status_code == 403
        uc.execute.assert_not_awaited()


class TestListUsersMailbox:
    def test_목록_항목에_mailbox_upn이_있다(self):
        from src.api.routes.admin_user_router import get_list_users_use_case
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=UserListResult(
            items=[UserListItem(id=7, email="kim@login.local", role="user",
                                status="approved", display_name="김", position=None,
                                mailbox_upn="kim@corp.com")],
            total=1,
        ))
        resp = _client({get_list_users_use_case: lambda: uc}).get("/api/v1/admin/users")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["mailbox_upn"] == "kim@corp.com"


class TestMcpPutNull:
    def test_JSON_null이_해제_의도로_UseCase까지_간다(self):
        """필드 없음과 null 을 구분해야 PUT 규칙이 성립한다 (model_fields_set)."""
        from src.api.routes.mcp_registry_router import (
            get_update_use_case,
            router,
        )
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=ValueError("stop"))
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_update_use_case] = lambda: uc
        client = TestClient(app)

        client.put("/api/v1/mcp-registry/srv-1", json={"identity_config": None})
        body = uc.execute.call_args.args[1]
        assert "identity_config" in body.model_fields_set
        client.put("/api/v1/mcp-registry/srv-1", json={"name": "n"})
        assert "identity_config" not in uc.execute.call_args.args[1].model_fields_set
