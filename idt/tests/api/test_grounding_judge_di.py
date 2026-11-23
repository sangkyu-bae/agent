"""grounding_judge_di — 공급자 조립·라우터 등록 (answer-citation-verification §9.1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.grounding_judge_di import (
    build_grounding_judge_provider,
    wire_grounding_judge,
)
from src.api.routes.admin_grounding_judge_router import (
    get_grounding_judge_setting_use_case,
)
from src.application.grounding_judge_setting.provider import (
    AdminConfiguredJudgeLlmProvider,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user


def test_build_provider_wraps_fallback():
    fallback = AsyncMock()
    provider = build_grounding_judge_provider(
        fallback=fallback,
        llm_factory=MagicMock(),
        session_factory=MagicMock(),
        logger=MagicMock(),
        ttl_seconds=30,
    )
    assert isinstance(provider, AdminConfiguredJudgeLlmProvider)


def test_wire_registers_routes_and_use_case_override():
    app = FastAPI()
    wire_grounding_judge(
        app,
        get_session=MagicMock(),
        provider=AsyncMock(),
        env_model_name="gpt-4o",
        logger=MagicMock(),
    )
    assert get_grounding_judge_setting_use_case in app.dependency_overrides
    # 위키: 라우트 등록은 app.routes 순회가 아니라 실요청으로 확인한다.
    app.dependency_overrides[get_current_user] = lambda: User(
        email="u@test.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )
    r = TestClient(app).get("/api/v1/admin/grounding-judge/settings")
    assert r.status_code == 403  # 404 가 아니면 등록됨(일반 사용자라 403)
