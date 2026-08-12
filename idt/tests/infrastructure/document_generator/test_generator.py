"""DocumentGenerator 단위 테스트 (doc-generator Design §4-4, D2·D5·D7)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.document_extractor.exceptions import McpToolNotConfiguredError
from src.domain.document_generator.exceptions import GenerateError
from src.domain.document_generator.schemas import (
    DocumentGenerationType,
    DocumentSection,
)
from src.domain.document_generator.tool_config import DocumentGeneratorToolConfig
from src.infrastructure.document_generator.generator import DocumentGenerator

_GOOD_HTML = (
    "<h1>시장조사 보고서</h1>"
    "<h2>개요</h2><p>내용</p>"
    "<h2>시장 현황</h2><p>내용</p>"
)


def _gen_type(**kwargs) -> DocumentGenerationType:
    now = datetime.now(timezone.utc)
    base = dict(
        id=str(uuid.uuid4()),
        agent_id="agent-1",
        worker_id="document_generator_worker",
        name="시장조사 보고서",
        description="시장 동향 조사",
        sections=[
            DocumentSection(title="개요"),
            DocumentSection(title="시장 현황", guidance="웹서치 근거 위주"),
        ],
        output_format="docx",
        status="active",
        created_at=now,
        updated_at=now,
    )
    base.update(kwargs)
    return DocumentGenerationType(**base)


def _tool_config(**kwargs) -> DocumentGeneratorToolConfig:
    base = dict(
        type_id="t-1", mcp_html_to_doc_tool_id="mcp_h2d", output_format="docx"
    )
    base.update(kwargs)
    return DocumentGeneratorToolConfig(**base)


def _llm(*contents: str):
    llm = MagicMock()
    responses = [MagicMock(content=c) for c in contents]
    llm.ainvoke = AsyncMock(side_effect=responses)
    return llm


def _stored(file_id="file-1", filename="시장조사 보고서.docx"):
    stored = MagicMock()
    stored.file_id = file_id
    stored.filename = filename
    return stored


def _generator(**kwargs):
    adapter = MagicMock()
    adapter.to_document = AsyncMock(return_value=b"doc-bytes")
    store = MagicMock()
    store.save = MagicMock(return_value=_stored())
    base = dict(
        conversion_adapter=adapter,
        attachment_store=store,
        logger=MagicMock(),
        default_html_to_doc_tool_id="",
        fallback_html_to_doc_tool_id="",
        llm_input_max_chars=20000,
    )
    base.update(kwargs)
    return DocumentGenerator(**base), adapter, store


class TestGenerateHappyPath:
    @pytest.mark.asyncio
    async def test_generates_converts_and_stores(self):
        generator, adapter, store = _generator()
        llm = _llm(_GOOD_HTML)

        result = await generator.generate(
            llm, _gen_type(), _tool_config(),
            evidence_block="근거 자료", conversation_block="대화",
            owner_user_id="7", request_id="req",
        )

        assert llm.ainvoke.await_count == 1
        adapter.to_document.assert_awaited_once()
        args = adapter.to_document.call_args
        assert "<h2>개요</h2>" in args.args[0]
        assert args.args[1] == "docx"
        assert args.args[2] == "mcp_h2d"

        store.save.assert_called_once()
        assert store.save.call_args.kwargs["filename"] == "시장조사 보고서.docx"
        assert result.file_id == "file-1"
        assert result.section_count == 2
        assert result.missing_sections == []
        assert result.used_evidence is True

    @pytest.mark.asyncio
    async def test_code_fence_stripped(self):
        generator, adapter, _ = _generator()
        llm = _llm(f"```html\n{_GOOD_HTML}\n```")
        await generator.generate(
            llm, _gen_type(), _tool_config(), "", "", "7", "req"
        )
        assert not adapter.to_document.call_args.args[0].startswith("```")

    @pytest.mark.asyncio
    async def test_script_sanitized_before_conversion(self):
        generator, adapter, _ = _generator()
        llm = _llm(_GOOD_HTML + "<script>alert(1)</script>")
        await generator.generate(
            llm, _gen_type(), _tool_config(), "", "", "7", "req"
        )
        assert "<script>" not in adapter.to_document.call_args.args[0]

    @pytest.mark.asyncio
    async def test_no_evidence_marks_prompt_and_result(self):
        generator, _, _ = _generator()
        llm = _llm(_GOOD_HTML)
        result = await generator.generate(
            llm, _gen_type(), _tool_config(), "", "대화", "7", "req"
        )
        user_message = llm.ainvoke.call_args.args[0][1]["content"]
        assert "수집된 근거 없음" in user_message
        assert result.used_evidence is False

    @pytest.mark.asyncio
    async def test_long_evidence_truncated(self):
        generator, _, _ = _generator(llm_input_max_chars=100)
        llm = _llm(_GOOD_HTML)
        await generator.generate(
            llm, _gen_type(), _tool_config(), "가" * 500, "나" * 500, "7", "req"
        )
        user_message = llm.ainvoke.call_args.args[0][1]["content"]
        assert user_message.count("가") == 100
        assert user_message.count("나") == 100


class TestSectionCoverageRetry:
    @pytest.mark.asyncio
    async def test_missing_section_retried_once_then_ok(self):
        generator, adapter, _ = _generator()
        incomplete = "<h1>보고서</h1><h2>개요</h2>"
        llm = _llm(incomplete, _GOOD_HTML)

        result = await generator.generate(
            llm, _gen_type(), _tool_config(), "", "", "7", "req"
        )

        assert llm.ainvoke.await_count == 2
        # 재시도 지시에 누락 섹션 명시
        retry_messages = llm.ainvoke.call_args.args[0]
        assert any("시장 현황" in str(m.get("content", "")) for m in retry_messages)
        assert result.missing_sections == []
        assert "시장 현황" in adapter.to_document.call_args.args[0]

    @pytest.mark.asyncio
    async def test_still_missing_after_retry_proceeds_with_record(self):
        generator, adapter, _ = _generator()
        incomplete = "<h1>보고서</h1><h2>개요</h2>"
        llm = _llm(incomplete, incomplete)

        result = await generator.generate(
            llm, _gen_type(), _tool_config(), "", "", "7", "req"
        )

        assert llm.ainvoke.await_count == 2
        adapter.to_document.assert_awaited_once()  # 부분 산출물이라도 진행 (D2)
        assert result.missing_sections == ["시장 현황"]

    @pytest.mark.asyncio
    async def test_empty_content_both_attempts_raises(self):
        generator, _, _ = _generator()
        llm = _llm("", "   ")
        with pytest.raises(GenerateError):
            await generator.generate(
                llm, _gen_type(), _tool_config(), "", "", "7", "req"
            )


class TestMcpToolFallbackChain:
    @pytest.mark.asyncio
    async def test_config_tool_id_wins(self):
        generator, adapter, _ = _generator(
            default_html_to_doc_tool_id="mcp_default",
            fallback_html_to_doc_tool_id="mcp_extractor",
        )
        await generator.generate(
            _llm(_GOOD_HTML), _gen_type(), _tool_config(), "", "", "7", "req"
        )
        assert adapter.to_document.call_args.args[2] == "mcp_h2d"

    @pytest.mark.asyncio
    async def test_empty_config_falls_back_to_default_then_extractor(self):
        generator, adapter, _ = _generator(
            default_html_to_doc_tool_id="mcp_default",
            fallback_html_to_doc_tool_id="mcp_extractor",
        )
        config = _tool_config(mcp_html_to_doc_tool_id="")
        await generator.generate(
            _llm(_GOOD_HTML), _gen_type(), config, "", "", "7", "req"
        )
        assert adapter.to_document.call_args.args[2] == "mcp_default"

        generator2, adapter2, _ = _generator(
            default_html_to_doc_tool_id="",
            fallback_html_to_doc_tool_id="mcp_extractor",
        )
        await generator2.generate(
            _llm(_GOOD_HTML), _gen_type(), config, "", "", "7", "req"
        )
        assert adapter2.to_document.call_args.args[2] == "mcp_extractor"

    @pytest.mark.asyncio
    async def test_all_empty_raises_not_configured(self):
        generator, _, _ = _generator()
        with pytest.raises(McpToolNotConfiguredError):
            await generator.generate(
                _llm(_GOOD_HTML), _gen_type(),
                _tool_config(mcp_html_to_doc_tool_id=""), "", "", "7", "req",
            )


class TestOutputFormat:
    @pytest.mark.asyncio
    async def test_pdf_format_from_tool_config(self):
        generator, adapter, store = _generator()
        store.save = MagicMock(
            return_value=_stored(filename="시장조사 보고서.pdf")
        )
        await generator.generate(
            _llm(_GOOD_HTML), _gen_type(), _tool_config(output_format="pdf"),
            "", "", "7", "req",
        )
        assert adapter.to_document.call_args.args[1] == "pdf"
        assert store.save.call_args.kwargs["filename"] == "시장조사 보고서.pdf"
