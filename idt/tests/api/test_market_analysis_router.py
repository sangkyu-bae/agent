"""시장 분석 라우터 — 접근 API·권한 의존성
(stock-analysis-agents design §5.1, §5.3, DD10).

Plan FR-15 · SC-6: 권한 없는 사용자는 메뉴가 보이지 않고(can_view=false) API 는 403.
"""

from unittest.mock import MagicMock

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from src.api.routes import market_analysis_router as ma_router
from src.application.market_analysis.access import GetAccessUseCase
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.market_analysis.access import MANAGE_CODE, VIEW_CODE
from src.interfaces.dependencies.auth import get_current_user

ACCESS = "/api/v1/market-analysis/access"


class FakeCodes:
    def __init__(self, codes: frozenset[str] = frozenset()):
        self.codes = codes

    async def codes_for(
        self, user_id: int, role: str, request_id: str
    ) -> frozenset[str]:
        return self.codes


def _user(role: UserRole = UserRole.USER, uid: int = 7) -> User:
    return User(
        email="x@t", password_hash="h", role=role, status=UserStatus.APPROVED, id=uid
    )


def _client(user: User | None, codes: frozenset[str] = frozenset()) -> TestClient:
    app = FastAPI()
    app.include_router(ma_router.router)

    # 뒤 모듈이 붙일 보호 경로를 흉내 낸다 — 의존성 동작만 본다
    @app.get("/probe/view")
    async def _view(u: User = Depends(ma_router.require_view)):
        return {"ok": u.id}

    @app.get("/probe/manage")
    async def _manage(u: User = Depends(ma_router.require_manage)):
        return {"ok": u.id}

    app.dependency_overrides[ma_router.get_access_use_case] = lambda: GetAccessUseCase(
        FakeCodes(codes), MagicMock()
    )
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_access_for_user_without_permission():
    res = _client(_user()).get(ACCESS)
    assert res.status_code == 200
    assert res.json() == {"enabled": True, "can_view": False, "can_manage": False}


def test_access_for_viewer_and_admin():
    assert _client(_user(), frozenset({VIEW_CODE})).get(ACCESS).json() == {
        "enabled": True,
        "can_view": True,
        "can_manage": False,
    }
    assert _client(_user(UserRole.ADMIN, 1)).get(ACCESS).json() == {
        "enabled": True,
        "can_view": True,
        "can_manage": True,
    }


def test_access_requires_login():
    res = _client(None).get(ACCESS)
    assert res.status_code in (401, 403)


def test_require_view_blocks_without_permission():
    res = _client(_user()).get("/probe/view")
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "MA_FORBIDDEN"


def test_require_view_passes_viewer_but_manage_does_not():
    client = _client(_user(), frozenset({VIEW_CODE}))
    assert client.get("/probe/view").json() == {"ok": 7}
    res = client.get("/probe/manage")
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "MA_FORBIDDEN"


def test_require_manage_passes_manager():
    assert _client(_user(), frozenset({MANAGE_CODE})).get("/probe/manage").json() == {
        "ok": 7
    }
