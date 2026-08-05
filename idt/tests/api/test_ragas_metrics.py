"""API 테스트: GET /api/ragas/metrics 메트릭 카탈로그 (eval-hub Design A7)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.ragas_router import router
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.ragas.policies import TARGET_METRICS
from src.domain.ragas.value_objects import MetricType
from src.interfaces.dependencies.auth import get_current_user


def _user() -> User:
    return User(
        email="u@example.com", password_hash="h",
        role=UserRole("user"), status=UserStatus.APPROVED, id=7,
    )


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _user()
    return TestClient(app)


class TestMetricCatalog:
    def test_전체_메트릭_반환(self, client):
        r = client.get("/api/ragas/metrics")
        assert r.status_code == 200
        body = r.json()
        keys = {m["key"] for m in body}
        assert keys == {m.value for m in MetricType}

    def test_스키마_필드(self, client):
        body = client.get("/api/ragas/metrics").json()
        for m in body:
            assert set(m) == {
                "key", "name", "description", "target_types", "requires_ground_truth",
            }
            assert m["name"] and m["description"]
            assert isinstance(m["target_types"], list)

    def test_target_매핑이_policies와_일치(self, client):
        body = client.get("/api/ragas/metrics").json()
        by_key = {m["key"]: set(m["target_types"]) for m in body}
        for target, metrics in TARGET_METRICS.items():
            for mt in metrics:
                assert target in by_key[mt.value]

    def test_ground_truth_필요_표시(self, client):
        body = client.get("/api/ragas/metrics").json()
        by_key = {m["key"]: m["requires_ground_truth"] for m in body}
        assert by_key["context_recall"] is True
        assert by_key["answer_correctness"] is True
        assert by_key["faithfulness"] is False
