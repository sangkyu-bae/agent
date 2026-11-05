"""/api/v1/agents/pipeline kb_id 전달·에코 — Design §8.2 #14~#16."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.agent_pipeline_router import (
    get_agent_pipeline_use_case,
    router,
)
from src.interfaces.dependencies.auth import get_current_user

from tests.api.test_agent_pipeline_router import (
    StubPipeline,
    _created_items,
    _user,
)

_URL = "/api/v1/agents/pipeline"


def _client(stub: StubPipeline) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent_pipeline_use_case] = lambda: stub
    app.dependency_overrides[get_current_user] = lambda: _user()
    return TestClient(app)


def test_kb_id_is_forwarded_to_use_case() -> None:
    stub = StubPipeline(_created_items())
    resp = _client(stub).post(
        _URL, json={"user_request": "문서 봇", "kb_id": "kb-1"}
    )
    assert resp.status_code == 200
    assert stub.calls[0]["kb_id"] == "kb-1"


def test_missing_kb_id_defaults_to_none_and_response_echoes_null() -> None:
    stub = StubPipeline(_created_items())
    resp = _client(stub).post(_URL, json={"user_request": "문서 봇"})
    assert resp.status_code == 200
    assert stub.calls[0]["kb_id"] is None
    assert resp.json()["kb_id"] is None


def test_response_echoes_outcome_kb_id() -> None:
    from dataclasses import replace

    items = _created_items()
    items[-1] = replace(items[-1], kb_id="kb-1")
    stub = StubPipeline(items)
    resp = _client(stub).post(_URL, json={"user_request": "문서 봇", "kb_id": "kb-1"})
    assert resp.json()["kb_id"] == "kb-1"


def test_unreadable_kb_is_422_from_use_case_value_error() -> None:
    stub = StubPipeline([ValueError("No read access to knowledge base 'kb-x'")])
    resp = _client(stub).post(_URL, json={"user_request": "문서 봇", "kb_id": "kb-x"})
    assert resp.status_code == 422
