"""Tests for AnalysisRouter."""

import io
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes.analysis_router import router, get_analyze_excel_use_case
from src.domain.entities.analysis_result import AnalysisAttempt, AnalysisResult


def _make_result(
    request_id: str = "test-123",
    is_successful: bool = True,
    with_code: bool = False,
) -> AnalysisResult:
    attempts = [
        AnalysisAttempt(
            attempt_number=1,
            analysis_text="분석 결과",
            confidence_score=0.9,
            hallucination_score=0.1,
            used_web_search=False,
            timestamp=datetime(2025, 2, 7, 10, 0, 0),
        )
    ]
    return AnalysisResult(
        request_id=request_id,
        user_query="데이터 요약",
        excel_summary={"rows": 100},
        final_answer="분석 결과",
        is_successful=is_successful,
        attempts=attempts,
        executed_code="print('hello')" if with_code else None,
        code_output={"output": "hello"} if with_code else None,
        created_at=datetime(2025, 2, 7, 10, 0, 0),
    )


def _create_test_client(mock_use_case) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_analyze_excel_use_case] = lambda: mock_use_case
    return TestClient(app)


class TestAnalysisRouter:

    def test_analyze_excel_success(self):
        mock_use_case = Mock()
        mock_use_case.execute = AsyncMock(return_value=_make_result())

        client = _create_test_client(mock_use_case)

        file_content = b"fake excel content"
        response = client.post(
            "/api/v1/analysis/excel",
            files={"file": ("test.xlsx", io.BytesIO(file_content), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"query": "데이터 요약", "user_id": "user-1"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["request_id"] == "test-123"
        assert body["is_successful"] is True
        assert body["total_attempts"] == 1
        assert body["final_answer"] == "분석 결과"
        assert len(body["attempts"]) == 1

    def test_analyze_excel_with_code(self):
        mock_use_case = Mock()
        mock_use_case.execute = AsyncMock(
            return_value=_make_result(with_code=True)
        )

        client = _create_test_client(mock_use_case)

        response = client.post(
            "/api/v1/analysis/excel",
            files={"file": ("test.xlsx", io.BytesIO(b"data"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"query": "그래프 그려줘", "user_id": "user-1"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["executed_code"] == "print('hello')"
        assert body["code_output"] == {"output": "hello"}

    def test_analyze_excel_failure(self):
        mock_use_case = Mock()
        mock_use_case.execute = AsyncMock(
            return_value=_make_result(is_successful=False)
        )

        client = _create_test_client(mock_use_case)

        response = client.post(
            "/api/v1/analysis/excel",
            files={"file": ("test.xlsx", io.BytesIO(b"data"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"query": "분석", "user_id": "user-1"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["is_successful"] is False

    def test_analyze_excel_internal_error(self):
        mock_use_case = Mock()
        mock_use_case.execute = AsyncMock(
            side_effect=RuntimeError("Unexpected error")
        )

        client = _create_test_client(mock_use_case)

        response = client.post(
            "/api/v1/analysis/excel",
            files={"file": ("test.xlsx", io.BytesIO(b"data"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"query": "분석", "user_id": "user-1"},
        )

        assert response.status_code == 500

    def test_analyze_excel_missing_query(self):
        mock_use_case = Mock()
        client = _create_test_client(mock_use_case)

        response = client.post(
            "/api/v1/analysis/excel",
            files={"file": ("test.xlsx", io.BytesIO(b"data"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"user_id": "user-1"},
        )

        assert response.status_code == 422
