"""/api/v1/agents/pipeline document_template·document_requests.

wizard-template-request Design §4.2 / §8.2 L1.

additive 계약: 신규 필드를 안 주면 기존 응답에 기본값만 더해진다.
템플릿 검증 예외(DocumentExtractorError)는 422 (동기) / stage_failed (SSE).
"""
from dataclasses import replace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.agent_pipeline_router import (
    get_agent_pipeline_use_case,
    router,
)
from src.application.agent_create_pipeline.events import StageEvent
from src.domain.agent_create_pipeline.policies import (
    EXTRACTOR_TOOL_ID,
    DocumentRequest,
    DocumentRequestKind,
)
from src.domain.agent_create_pipeline.stages import (
    PipelineStage,
    StageRecord,
    StageStatus,
)
from src.domain.document_extractor.exceptions import InvalidSlotError
from src.interfaces.dependencies.auth import get_current_user

from tests.api.test_agent_pipeline_router import (
    StubPipeline,
    _created_items,
    _parse_sse,
    _record,
    _stage_events,
    _user,
)

_URL = "/api/v1/agents/pipeline"

_TEMPLATE = {
    "name": "여신심의서",
    "html_skeleton": "<p>{{company}}</p>",
    "slots": [{"key": "company", "label": "회사명", "slot_type": "value"}],
    "source_file_id": "file-1",
    "source_format": "docx",
    "mcp_pdf_to_html_tool_id": "mcp:pdf",
    "mcp_html_to_doc_tool_id": "mcp:doc",
}


def _client(stub: StubPipeline, raise_server_exceptions=True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent_pipeline_use_case] = lambda: stub
    app.dependency_overrides[get_current_user] = lambda: _user()
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _request() -> DocumentRequest:
    return DocumentRequest(
        tool_id=EXTRACTOR_TOOL_ID,
        kind=DocumentRequestKind.FORM_TEMPLATE,
        message="여신심의서에 쓸 양식 파일(PDF 또는 DOCX)을 올려주세요.",
    )


# ── 요청 전달 (L1-06·L1-09) ─────────────────────────────────────────────────


def test_document_template_is_forwarded_as_schema_object() -> None:
    stub = StubPipeline(_created_items())
    resp = _client(stub).post(
        _URL, json={"user_request": "양식 봇", "document_template": _TEMPLATE}
    )
    assert resp.status_code == 200
    forwarded = stub.calls[0]["document_template"]
    assert forwarded is not None
    assert forwarded.name == "여신심의서"
    assert forwarded.slots[0].key == "company"


def test_missing_template_defaults_to_none() -> None:
    stub = StubPipeline(_created_items())
    _client(stub).post(_URL, json={"user_request": "양식 봇"})
    assert stub.calls[0]["document_template"] is None


def test_invalid_template_body_is_422_before_use_case() -> None:
    stub = StubPipeline(_created_items())
    bad = {**_TEMPLATE, "slots": []}  # min_length=1
    resp = _client(stub).post(
        _URL, json={"user_request": "양식 봇", "document_template": bad}
    )
    assert resp.status_code == 422
    assert stub.calls == []


# ── 응답 additive (L1-01·L1-02·L1-05) ───────────────────────────────────────


def test_legacy_body_gets_default_new_fields() -> None:
    stub = StubPipeline(_created_items())
    body = _client(stub).post(_URL, json={"user_request": "양식 봇"}).json()
    assert body["document_requests"] == []
    assert body["document_template_attached"] is False


def test_response_serializes_document_requests() -> None:
    items = _created_items()
    items[-1] = replace(
        items[-1], document_requests=(_request(),), document_template_attached=True
    )
    resp = _client(StubPipeline(items)).post(_URL, json={"user_request": "양식 봇"})
    body = resp.json()
    assert body["document_template_attached"] is True
    assert body["document_requests"] == [
        {
            "tool_id": EXTRACTOR_TOOL_ID,
            "kind": "form_template",
            "message": "여신심의서에 쓸 양식 파일(PDF 또는 DOCX)을 올려주세요.",
            "accept": ["pdf", "docx"],
        }
    ]


# ── 에러 매핑 (L1-07·L1-08) ─────────────────────────────────────────────────


def test_template_without_extractor_value_error_is_422() -> None:
    stub = StubPipeline(
        [ValueError("문서추출기 도구가 없는 에이전트에는 양식을 등록할 수 없습니다")]
    )
    resp = _client(stub).post(
        _URL, json={"user_request": "양식 봇", "document_template": _TEMPLATE}
    )
    assert resp.status_code == 422
    assert "문서추출기" in resp.json()["detail"]


def test_template_validation_error_is_422_sync() -> None:
    stub = StubPipeline([InvalidSlotError("slot key 'a b' is invalid")])
    resp = _client(stub).post(
        _URL, json={"user_request": "양식 봇", "document_template": _TEMPLATE}
    )
    assert resp.status_code == 422
    assert "slot key" in resp.json()["detail"]


def test_template_validation_error_is_stage_failed_in_sse() -> None:
    stub = StubPipeline([
        *_stage_events(_record(PipelineStage.INTENT)),
        *_stage_events(_record(PipelineStage.TOOLS)),
        *_stage_events(_record(PipelineStage.PROMPT)),
        StageEvent(
            "stage_started", StageRecord(PipelineStage.CREATE, StageStatus.OK)
        ),
        InvalidSlotError("slot key 'a b' is invalid"),
    ])
    events = _parse_sse(
        _client(stub).post(f"{_URL}/stream", json={"user_request": "양식 봇"}).text
    )
    kinds = [name for name, _, _ in events]
    assert kinds[-2:] == ["stage_failed", "pipeline_result"]
    failed = events[-2][2]
    assert failed["stage"] == "create"
    assert "slot key" in failed["reason"]


# ── 동기 == SSE (L1-10) ─────────────────────────────────────────────────────


def test_sse_final_payload_equals_sync_response_with_new_fields() -> None:
    items = _created_items()
    items[-1] = replace(
        items[-1], document_requests=(_request(),), document_template_attached=True
    )
    client = _client(StubPipeline(items))
    sync = client.post(_URL, json={"user_request": "양식 봇"}).json()
    client2 = _client(StubPipeline(items))
    events = _parse_sse(
        client2.post(f"{_URL}/stream", json={"user_request": "양식 봇"}).text
    )
    assert events[-1][0] == "pipeline_result"
    assert events[-1][2] == sync
