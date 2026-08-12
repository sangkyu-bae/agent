"""document_generation_type ↔ 에이전트 바인딩 테스트 (doc-generator Design §4-3)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.document_generation_type_binding import (
    DOCUMENT_GENERATOR_TOOL_ID,
    build_document_generation_type_plan,
    ensure_generation_type_wiring,
    persist_document_generation_type,
)
from src.application.agent_builder.schemas import (
    DocumentGenerationTypeRequest,
    DocumentSectionRequest,
)
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.document_generator.exceptions import InvalidGenerationTypeError


def _worker(tool_id=DOCUMENT_GENERATOR_TOOL_ID) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id,
        worker_id=f"{tool_id}_worker",
        description="문서생성기",
    )


def _type_request(**kwargs) -> DocumentGenerationTypeRequest:
    base = dict(
        name="시장조사 보고서",
        description="특정 주제의 시장 동향 조사",
        sections=[
            DocumentSectionRequest(title="개요"),
            DocumentSectionRequest(title="시장 현황", guidance="웹서치 근거 위주"),
        ],
        output_format="docx",
        mcp_html_to_doc_tool_id="mcp_h2d",
    )
    base.update(kwargs)
    return DocumentGenerationTypeRequest(**base)


class TestBuildPlan:
    def test_plan_built_and_tool_config_injected(self):
        worker = _worker()
        plan = build_document_generation_type_plan(
            _type_request(), [worker], max_sections=20
        )

        assert plan.worker_id == "document_generator_worker"
        assert plan.name == "시장조사 보고서"
        assert [s.title for s in plan.sections] == ["개요", "시장 현황"]
        assert plan.sections[1].guidance == "웹서치 근거 위주"
        assert plan.output_format == "docx"

        assert worker.tool_config["type_id"] == plan.type_id
        assert worker.tool_config["mcp_html_to_doc_tool_id"] == "mcp_h2d"
        assert worker.tool_config["output_format"] == "docx"

    def test_missing_generator_worker_rejected(self):
        with pytest.raises(ValueError, match="document_generator"):
            build_document_generation_type_plan(
                _type_request(), [_worker("excel_export")], max_sections=20
            )

    def test_empty_sections_rejected(self):
        with pytest.raises(InvalidGenerationTypeError):
            build_document_generation_type_plan(
                _type_request(sections=[]), [_worker()], max_sections=20
            )

    def test_invalid_output_format_rejected(self):
        with pytest.raises(InvalidGenerationTypeError):
            build_document_generation_type_plan(
                _type_request(output_format="hwp"), [_worker()], max_sections=20
            )

    def test_empty_mcp_tool_id_allowed(self):
        """D5: 미지정 시 settings 폴백 — 빈 값 저장 허용."""
        worker = _worker()
        build_document_generation_type_plan(
            _type_request(mcp_html_to_doc_tool_id=""), [worker], max_sections=20
        )
        assert worker.tool_config["mcp_html_to_doc_tool_id"] == ""


class TestPersist:
    @pytest.mark.asyncio
    async def test_persist_saves_active_type(self):
        repo = MagicMock()
        repo.save = AsyncMock(side_effect=lambda t, rid: t)
        plan = build_document_generation_type_plan(
            _type_request(), [_worker()], max_sections=20
        )

        saved = await persist_document_generation_type(plan, "agent-1", repo, "req")

        repo.save.assert_awaited_once()
        assert saved.agent_id == "agent-1"
        assert saved.id == plan.type_id
        assert saved.status == "active"
        assert saved.output_format == "docx"


class TestEnsureWiring:
    def test_missing_repo_rejected(self):
        with pytest.raises(ValueError, match="문서 유형"):
            ensure_generation_type_wiring(None)

    def test_wired_repo_passes(self):
        ensure_generation_type_wiring(MagicMock())
