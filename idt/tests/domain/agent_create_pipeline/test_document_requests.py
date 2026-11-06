"""PipelinePolicy 문서 요청 — wizard-template-request Design §4.2 / Plan FR-01~03·FR-05.

요청은 **확정 도구 목록의 함수**다(declared-slot-elicitation). LLM 호출 없음.
"""
import pytest
from src.domain.agent_create_pipeline.policies import (
    EXTRACTOR_TOOL_ID,
    DocumentRequest,
    DocumentRequestKind,
    PipelinePolicy,
)
from src.domain.intent.schemas import IntentResult


def _intent(purpose: str | None = "여신심의서 작성", degraded=False) -> IntentResult:
    slots = {"purpose": purpose} if purpose else {}
    return IntentResult(complete=True, filled_slots=slots, degraded=degraded)


# ── 판단 트리거 (FR-01·FR-03) ───────────────────────────────────────────────


def test_extractor_tool_id_is_catalog_form() -> None:
    assert EXTRACTOR_TOOL_ID == "internal:document_extractor"


def test_no_extractor_returns_empty() -> None:
    assert PipelinePolicy.document_requests_for(("internal:a",), _intent()) == ()


def test_extractor_present_returns_single_form_template_request() -> None:
    requests = PipelinePolicy.document_requests_for(
        ("internal:a", EXTRACTOR_TOOL_ID), _intent()
    )
    assert len(requests) == 1
    req = requests[0]
    assert isinstance(req, DocumentRequest)
    assert req.tool_id == EXTRACTOR_TOOL_ID
    assert req.kind == DocumentRequestKind.FORM_TEMPLATE
    assert req.accept == ("pdf", "docx")


def test_kind_wire_value_is_stable() -> None:
    assert DocumentRequestKind.FORM_TEMPLATE.value == "form_template"


# ── 문구 (FR-02) ────────────────────────────────────────────────────────────


def test_message_includes_purpose_when_available() -> None:
    (req,) = PipelinePolicy.document_requests_for((EXTRACTOR_TOOL_ID,), _intent())
    assert req.message.startswith("여신심의서 작성에 쓸 양식 파일")
    assert "PDF 또는 DOCX" in req.message


def test_message_falls_back_without_purpose() -> None:
    (req,) = PipelinePolicy.document_requests_for(
        (EXTRACTOR_TOOL_ID,), _intent(purpose=None)
    )
    assert req.message.startswith("이 에이전트가 채울 양식 파일")


def test_message_ignores_degraded_intent_slots() -> None:
    (req,) = PipelinePolicy.document_requests_for(
        (EXTRACTOR_TOOL_ID,), _intent(degraded=True)
    )
    assert "여신심의서" not in req.message


def test_message_handles_none_intent() -> None:
    (req,) = PipelinePolicy.document_requests_for((EXTRACTOR_TOOL_ID,), None)
    assert req.message.startswith("이 에이전트가 채울 양식 파일")


def test_message_normalizes_purpose_whitespace() -> None:
    (req,) = PipelinePolicy.document_requests_for(
        (EXTRACTOR_TOOL_ID,), _intent(purpose="  여신  심의서\n작성 ")
    )
    assert req.message.startswith("여신 심의서 작성에 쓸")


# ── 정합 검증 (FR-05) ───────────────────────────────────────────────────────


def test_validate_template_tools_passes_without_template() -> None:
    PipelinePolicy.validate_template_tools(("internal:a",), has_template=False)


def test_validate_template_tools_passes_with_extractor() -> None:
    PipelinePolicy.validate_template_tools(
        ("internal:a", EXTRACTOR_TOOL_ID), has_template=True
    )


def test_validate_template_tools_rejects_template_without_extractor() -> None:
    with pytest.raises(ValueError, match="문서추출기"):
        PipelinePolicy.validate_template_tools(("internal:a",), has_template=True)
