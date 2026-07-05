"""DocumentComposer 테스트 (Design §4-3, D6).

핵심 검증: 토큰 치환 재현성 · HTML escape · GB6 공란+하이라이트 · JSON 계약 재시도.
"""
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.domain.agent_attachment.value_objects import (
    AttachmentType,
    StoredAttachment,
)
from src.domain.document_extractor.exceptions import ComposeError, McpConversionError
from src.domain.document_extractor.schemas import DocumentTemplate, TemplateSlot
from src.domain.document_extractor.tool_config import DocumentExtractorToolConfig
from src.infrastructure.document_extractor.composer import DocumentComposer


class FakeLLM:
    def __init__(self, contents: list[str]):
        self._contents = list(contents)
        self.call_count = 0

    async def ainvoke(self, messages):
        self.call_count += 1
        response = MagicMock()
        response.content = self._contents.pop(0)
        return response


class FakeAdapter:
    def __init__(self, error: Exception | None = None):
        self.html_received = None
        self._error = error

    async def to_document(self, html, output_format, mcp_tool_id, request_id):
        if self._error:
            raise self._error
        self.html_received = html
        return b"FILE-BYTES"


class FakeStore:
    def save(self, *, file_bytes, filename, attachment_type, owner_user_id):
        return StoredAttachment(
            file_id="c" * 32, type=attachment_type, filename=filename,
            size=len(file_bytes), owner_user_id=owner_user_id,
            file_path="/tmp/out",
        )


def _template() -> DocumentTemplate:
    now = datetime.now(timezone.utc)
    return DocumentTemplate(
        id=str(uuid.uuid4()), agent_id="agent-1",
        worker_id="document_extractor_worker", name="여신심의서",
        html_skeleton="<p>금액: {{loan_amount}}</p><p>소견: {{opinion}}</p>",
        slots=[
            TemplateSlot(key="loan_amount", label="여신금액", slot_type="value"),
            TemplateSlot(key="opinion", label="소견", slot_type="generated"),
        ],
        source_file_ref="ref", source_format="pdf", status="active",
        created_at=now, updated_at=now,
    )


def _config() -> DocumentExtractorToolConfig:
    return DocumentExtractorToolConfig(
        template_id="t-1", mcp_pdf_to_html_tool_id="mcp_p2h",
        mcp_html_to_doc_tool_id="mcp_h2d", output_format="pdf",
    )


def _composer(adapter=None) -> tuple[DocumentComposer, FakeAdapter]:
    adapter = adapter or FakeAdapter()
    return DocumentComposer(
        conversion_adapter=adapter,
        attachment_store=FakeStore(),
        logger=MagicMock(),
    ), adapter


async def _compose(composer, llm, **kwargs):
    defaults = dict(
        llm=llm, template=_template(), tool_config=_config(),
        evidence_block="[근거] oo문서: 소견 근거 내용",
        conversation_block="여신금액 5억으로 심의서 작성해줘",
        owner_user_id="7", request_id="req",
    )
    defaults.update(kwargs)
    return await composer.compose(**defaults)


class TestCompose:
    @pytest.mark.asyncio
    async def test_happy_path_fills_and_saves_file(self):
        llm = FakeLLM([json.dumps(
            {"loan_amount": "5억 원", "opinion": "근거 기반 소견"},
            ensure_ascii=False,
        )])
        composer, adapter = _composer()
        result = await _compose(composer, llm)
        assert result.file_id == "c" * 32
        assert result.filename == "여신심의서.pdf"
        assert "5억 원" in adapter.html_received
        assert "{{" not in adapter.html_received     # 토큰 잔류 없음
        assert result.filled_slots == {"여신금액": "5억 원", "소견": "근거 기반 소견"}
        assert result.unfilled_labels == []

    @pytest.mark.asyncio
    async def test_replacement_is_deterministic(self):
        """토큰 치환 재현성: 같은 입력 → 같은 출력 HTML (방식 A)."""
        payload = json.dumps({"loan_amount": "5억", "opinion": "소견"})
        composer1, adapter1 = _composer()
        composer2, adapter2 = _composer()
        await _compose(composer1, FakeLLM([payload]))
        await _compose(composer2, FakeLLM([payload]))
        assert adapter1.html_received == adapter2.html_received

    @pytest.mark.asyncio
    async def test_values_html_escaped(self):
        llm = FakeLLM([json.dumps(
            {"loan_amount": "<b>5억</b>", "opinion": "소견"}
        )])
        composer, adapter = _composer()
        await _compose(composer, llm)
        assert "<b>5억</b>" not in adapter.html_received
        assert "&lt;b&gt;5억&lt;/b&gt;" in adapter.html_received

    @pytest.mark.asyncio
    async def test_token_injection_stripped(self):
        llm = FakeLLM([json.dumps(
            {"loan_amount": "5억 {{opinion}}", "opinion": "소견"}
        )])
        composer, adapter = _composer()
        await _compose(composer, llm)
        assert "{{opinion}}" not in adapter.html_received

    @pytest.mark.asyncio
    async def test_gb6_null_slot_left_blank_with_highlight(self):
        """GB6: 근거 없는 슬롯(null)은 공란+하이라이트, 추정값 미생성."""
        llm = FakeLLM([json.dumps({"loan_amount": "5억", "opinion": None})])
        composer, adapter = _composer()
        result = await _compose(composer, llm)
        assert 'data-unfilled="opinion"' in adapter.html_received
        assert result.unfilled_labels == ["소견"]
        assert "소견" not in result.filled_slots

    @pytest.mark.asyncio
    async def test_missing_key_retries_then_raises(self):
        """모든 슬롯 key 필수 (D6) — 재시도 후 파일 미생성."""
        incomplete = json.dumps({"loan_amount": "5억"})
        llm = FakeLLM([incomplete, incomplete])
        composer, adapter = _composer()
        with pytest.raises(ComposeError):
            await _compose(composer, llm)
        assert llm.call_count == 2
        assert adapter.html_received is None    # 변환 미호출 = 파일 미생성

    @pytest.mark.asyncio
    async def test_parse_failure_retries_then_raises(self):
        llm = FakeLLM(["not json", "still not json"])
        composer, _ = _composer()
        with pytest.raises(ComposeError):
            await _compose(composer, llm)

    @pytest.mark.asyncio
    async def test_code_fence_tolerated(self):
        payload = json.dumps({"loan_amount": "5억", "opinion": "소견"})
        llm = FakeLLM([f"```json\n{payload}\n```"])
        composer, _ = _composer()
        result = await _compose(composer, llm)
        assert result.unfilled_labels == []

    @pytest.mark.asyncio
    async def test_mcp_failure_propagates(self):
        llm = FakeLLM([json.dumps({"loan_amount": "5억", "opinion": "소견"})])
        composer, _ = _composer(adapter=FakeAdapter(error=McpConversionError("down")))
        with pytest.raises(McpConversionError):
            await _compose(composer, llm)

    @pytest.mark.asyncio
    async def test_docx_output_filename(self):
        llm = FakeLLM([json.dumps({"loan_amount": "5억", "opinion": "소견"})])
        composer, _ = _composer()
        config = DocumentExtractorToolConfig(
            template_id="t-1", mcp_pdf_to_html_tool_id="mcp_p2h",
            mcp_html_to_doc_tool_id="mcp_h2d", output_format="docx",
        )
        result = await _compose(composer, llm, tool_config=config)
        assert result.filename == "여신심의서.docx"
