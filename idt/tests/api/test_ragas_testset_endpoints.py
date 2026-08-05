"""API 테스트: 테스트셋 상세(cases)·업로드·생성초안·배치 에러 매핑 (eval-hub Design A2/A5/A6/A8)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.ragas_router import (
    router,
    get_batch_eval_use_case,
    get_testset_use_case,
    get_testset_generate_use_case,
)
from src.application.ragas.schemas import (
    GeneratedTestsetDraft,
    TestsetDetailResponse,
    TestsetResponse,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user

NOW = datetime(2026, 8, 3)


def _user() -> User:
    return User(
        email="u@example.com", password_hash="h",
        role=UserRole("user"), status=UserStatus.APPROVED, id=7,
    )


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    a.dependency_overrides[get_current_user] = lambda: _user()
    return a


class TestDetailCases:
    def test_상세에_cases_포함(self, app):
        uc = MagicMock()
        uc.get_detail = AsyncMock(return_value=TestsetDetailResponse(
            id="ts-1", name="셋", description="", case_count=2,
            created_at=NOW, user_id="7",
            cases=[
                {"question": "q1", "ground_truth": "a1"},
                {"question": "q2", "ground_truth": None},
            ],
        ))
        app.dependency_overrides[get_testset_use_case] = lambda: uc
        c = TestClient(app)

        r = c.get("/api/ragas/testsets/ts-1")
        assert r.status_code == 200
        body = r.json()
        assert len(body["cases"]) == 2
        assert body["cases"][0] == {"question": "q1", "ground_truth": "a1"}


class TestUpload:
    def test_파일_업로드_201(self, app):
        uc = MagicMock()
        uc.create_from_file = AsyncMock(return_value=TestsetResponse(
            id="ts-1", name="업로드셋", description="", case_count=2,
            created_at=NOW, user_id="7",
        ))
        app.dependency_overrides[get_testset_use_case] = lambda: uc
        c = TestClient(app)

        r = c.post(
            "/api/ragas/testsets/upload",
            data={"name": "업로드셋", "description": ""},
            files={"file": ("t.csv", b"question,ground_truth\nq,a\n", "text/csv")},
        )
        assert r.status_code == 201
        assert r.json()["case_count"] == 2
        assert uc.create_from_file.await_args.kwargs["user_id"] == "7"

    def test_파싱_실패_422(self, app):
        uc = MagicMock()
        uc.create_from_file = AsyncMock(side_effect=ValueError("question 컬럼이 없습니다"))
        app.dependency_overrides[get_testset_use_case] = lambda: uc
        c = TestClient(app)

        r = c.post(
            "/api/ragas/testsets/upload",
            data={"name": "셋"},
            files={"file": ("t.csv", b"a,b\n", "text/csv")},
        )
        assert r.status_code == 422


class TestGenerateDraft:
    def test_생성초안_200(self, app):
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=GeneratedTestsetDraft(
            source_filename="doc.pdf",
            items=[{"question": "q", "ground_truth": "a"}],
        ))
        app.dependency_overrides[get_testset_generate_use_case] = lambda: uc
        c = TestClient(app)

        r = c.post(
            "/api/ragas/testsets/generate",
            data={"max_pairs": "5"},
            files={"file": ("doc.pdf", b"%PDF-", "application/pdf")},
        )
        assert r.status_code == 200
        assert r.json()["items"][0]["question"] == "q"

    def test_지원안하는_형식_422(self, app):
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=ValueError("지원하지 않는 형식"))
        app.dependency_overrides[get_testset_generate_use_case] = lambda: uc
        c = TestClient(app)

        r = c.post(
            "/api/ragas/testsets/generate",
            files={"file": ("doc.hwp", b"x", "application/octet-stream")},
        )
        assert r.status_code == 422


class TestBatchErrorMapping:
    def _client(self, app, side_effect):
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=side_effect)
        app.dependency_overrides[get_batch_eval_use_case] = lambda: uc
        return TestClient(app)

    def test_테스트셋_없음_404(self, app):
        c = self._client(app, ValueError("테스트셋을 찾을 수 없습니다"))
        r = c.post("/api/ragas/batch", json={
            "target_type": "rag", "metrics": ["faithfulness"],
            "testcases": [], "testset_id": "ts-x",
        })
        assert r.status_code == 404

    def test_검증_실패_422(self, app):
        c = self._client(app, ValueError("테스트 케이스가 비어있습니다"))
        r = c.post("/api/ragas/batch", json={
            "target_type": "rag", "metrics": ["faithfulness"], "testcases": [],
        })
        assert r.status_code == 422
