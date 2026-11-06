"""파이프라인 document_template 전달·document_requests 계산.

wizard-template-request Design §4.2.

- 템플릿은 CreateAgentRequest.document_template 로 **그대로** 전달된다 (FR-04).
- 추출기 없는 템플릿은 저장 전 ValueError (FR-05 / D3).
- document_requests 는 모든 outcome 에서 확정 목록 기준으로 계산된다 (D1).
"""
import pytest
from src.application.agent_builder.schemas import DocumentTemplateRequest
from src.domain.agent_create_pipeline.policies import EXTRACTOR_TOOL_ID
from src.domain.agent_create_pipeline.stages import PipelineStop
from src.domain.intent.schemas import IntentResult, SlotQuestion
from src.domain.tool_selection.schemas import ToolCandidate

from tests.application.agent_create_pipeline.test_use_case import (
    FakeIntentUC,
    _drain,
    _outcome,
    _pipeline,
    _selection,
)


def _template() -> DocumentTemplateRequest:
    return DocumentTemplateRequest(
        name="여신심의서",
        html_skeleton="<p>{{company}}</p>",
        slots=[{"key": "company", "label": "회사명", "slot_type": "value",
                "sample_value": "ㅇㅇ상사"}],
        source_file_id="file-1",
        source_format="docx",
        mcp_pdf_to_html_tool_id="mcp:pdf",
        mcp_html_to_doc_tool_id="mcp:doc",
    )


def _with_extractor():
    """셀렉터가 추출기를 포함해 확정하는 파이프라인."""
    return _pipeline(
        candidates=(
            ToolCandidate(tool_id="internal:a", name="검색"),
            ToolCandidate(tool_id=EXTRACTOR_TOOL_ID, name="문서추출기"),
        ),
        selection=_selection(
            final=("internal:a", EXTRACTOR_TOOL_ID),
            selected=("internal:a", EXTRACTOR_TOOL_ID),
        ),
    )


# ── 템플릿 전달 (FR-04) ─────────────────────────────────────────────────────


async def test_template_is_forwarded_to_create_request_unchanged() -> None:
    use_case, fakes = _with_extractor()
    template = _template()
    events = await _drain(use_case, document_template=template)
    request = fakes["create"].calls[0]
    assert request.document_template is template
    outcome = _outcome(events)
    assert outcome.status == "created"
    assert outcome.document_template_attached is True


async def test_without_template_create_request_is_unchanged() -> None:
    use_case, fakes = _pipeline()
    events = await _drain(use_case)
    assert fakes["create"].calls[0].document_template is None
    assert _outcome(events).document_template_attached is False
    assert _outcome(events).document_requests == ()


# ── 정합 검증 (FR-05 / D3) ──────────────────────────────────────────────────


async def test_template_without_extractor_fails_before_create() -> None:
    use_case, fakes = _pipeline()  # final=("internal:a",)
    with pytest.raises(ValueError, match="문서추출기"):
        await _drain(use_case, document_template=_template())
    assert fakes["create"].calls == []


# ── document_requests 계산 (D1 / FR-01·FR-03) ───────────────────────────────


async def test_tools_proposed_carries_form_template_request() -> None:
    use_case, _ = _with_extractor()
    outcome = _outcome(
        await _drain(use_case, stop_after=PipelineStop.TOOLS)
    )
    assert outcome.status == "tools_proposed"
    assert [r.kind.value for r in outcome.document_requests] == ["form_template"]
    assert "문서 Q&A" in outcome.document_requests[0].message


async def test_confirmed_tools_without_extractor_yield_no_request() -> None:
    """사용자가 도구 단계에서 추출기를 뺀 경우 — 확정 목록 기준 (FR-03)."""
    use_case, _ = _with_extractor()
    outcome = _outcome(
        await _drain(
            use_case,
            stop_after=PipelineStop.PROMPT,
            tools_confirmed=True,
            tool_ids=("internal:a",),
        )
    )
    assert outcome.status == "prompt_ready"
    assert outcome.document_requests == ()


async def test_prompt_ready_echoes_template_attached_without_saving() -> None:
    use_case, fakes = _with_extractor()
    outcome = _outcome(
        await _drain(
            use_case,
            stop_after=PipelineStop.PROMPT,
            tools_confirmed=True,
            tool_ids=("internal:a", EXTRACTOR_TOOL_ID),
            document_template=_template(),
        )
    )
    assert outcome.document_template_attached is True
    assert fakes["create"].calls == []


def test_pipeline_does_not_bypass_template_binding_path() -> None:
    """AST 계약 (Design §7): 파이프라인은 템플릿 저장소·persist 를 직접 참조하지 않는다.

    검증(SlotPolicy·TemplateTokenPolicy)은 CreateAgentUseCase 의 기존 바인딩
    경로에서만 수행된다 — 여기에 우회 경로가 생기면 클라 입력이 미검증 저장된다.
    """
    import ast
    import inspect

    import src.application.agent_create_pipeline.use_case as module

    tree = ast.parse(inspect.getsource(module))
    names = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    forbidden = {
        "persist_document_template",
        "build_document_template_plan",
        "document_template_repo",
        "DocumentTemplateRepository",
    }
    assert not (names & forbidden), names & forbidden


async def test_need_input_has_empty_requests() -> None:
    intent = FakeIntentUC(
        IntentResult(
            complete=False,
            questions=[SlotQuestion(slot_key="purpose", question="용도는?")],
        )
    )
    use_case, _ = _pipeline(intent=intent)
    outcome = _outcome(await _drain(use_case))
    assert outcome.status == "need_input"
    assert outcome.document_requests == ()
