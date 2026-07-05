"""ExtractDocumentUseCase 테스트 — MCP/LLM/store 모의 (Design §3-2)."""
from unittest.mock import MagicMock

import pytest

from src.application.document_extractor.extract_use_case import (
    ExtractDocumentUseCase,
)
from src.domain.agent_attachment.value_objects import (
    AttachmentType,
    StoredAttachment,
)
from src.domain.document_extractor.exceptions import (
    DocumentTooLargeError,
    InvalidDocumentError,
    McpConversionError,
    McpToolNotConfiguredError,
)
from src.domain.document_extractor.schemas import SuggestedSlots, TemplateSlot


class FakeStore:
    def __init__(self):
        self.saved = None

    def save(self, *, file_bytes, filename, attachment_type, owner_user_id):
        self.saved = dict(
            filename=filename, type=attachment_type, owner=owner_user_id
        )
        return StoredAttachment(
            file_id="a" * 32,
            type=attachment_type,
            filename=filename,
            size=len(file_bytes),
            owner_user_id=owner_user_id,
            file_path="/tmp/fake",
        )


class FakeAdapter:
    def __init__(self, html="<p>양식 {{x}}</p>", preview_html="<p>layout</p>",
                 preview_error: Exception | None = None):
        self.html = html
        self.preview_html = preview_html
        self.preview_error = preview_error
        self.called_with = None
        self.calls: list[dict] = []

    async def to_html(self, file_bytes, source_format, mcp_tool_id, request_id,
                      options=None):
        call = dict(fmt=source_format, tool_id=mcp_tool_id, options=options)
        self.calls.append(call)
        self.called_with = call
        if options is not None:
            if self.preview_error:
                raise self.preview_error
            return self.preview_html
        return self.html


class FakeExtractor:
    async def extract(self, html, request_id):
        return SuggestedSlots(
            slots=[TemplateSlot(key="loan_amount", label="여신금액", slot_type="value")]
        )


def _use_case(store=None, adapter=None, **kwargs) -> ExtractDocumentUseCase:
    defaults = dict(
        attachment_store=store or FakeStore(),
        conversion_adapter=adapter or FakeAdapter(),
        slot_extractor=FakeExtractor(),
        logger=MagicMock(),
        max_file_mb=20,
        default_pdf_to_html_tool_id="mcp_default_p2h",
        default_html_to_doc_tool_id="mcp_default_h2d",
    )
    defaults.update(kwargs)
    return ExtractDocumentUseCase(**defaults)


class TestExtractDocumentUseCase:
    @pytest.mark.asyncio
    async def test_success_returns_html_slots_and_echoed_ids(self):
        store = FakeStore()
        uc = _use_case(store=store)
        result = await uc.execute(
            file_bytes=b"pdf",
            filename="심의서.pdf",
            owner_user_id="7",
            mcp_pdf_to_html_tool_id="mcp_custom",
            mcp_html_to_doc_tool_id=None,
            request_id="req",
        )
        assert result.source_file_id == "a" * 32
        assert result.source_format == "pdf"
        assert result.suggested_slots[0].key == "loan_amount"
        # 명시 지정 우선, 미지정은 settings 폴백 에코 (D5)
        assert result.mcp_pdf_to_html_tool_id == "mcp_custom"
        assert result.mcp_html_to_doc_tool_id == "mcp_default_h2d"
        assert store.saved["type"] == AttachmentType.DOCUMENT

    @pytest.mark.asyncio
    async def test_html_is_sanitized(self):
        adapter = FakeAdapter(html='<p>ok</p><script>bad()</script>')
        uc = _use_case(adapter=adapter)
        result = await uc.execute(
            file_bytes=b"pdf", filename="a.pdf", owner_user_id="7",
            mcp_pdf_to_html_tool_id=None, mcp_html_to_doc_tool_id=None,
            request_id="req",
        )
        assert "<script" not in result.html

    @pytest.mark.asyncio
    async def test_docx_format_resolved(self):
        adapter = FakeAdapter()
        uc = _use_case(adapter=adapter)
        result = await uc.execute(
            file_bytes=b"docx", filename="양식.DOCX", owner_user_id="7",
            mcp_pdf_to_html_tool_id=None, mcp_html_to_doc_tool_id=None,
            request_id="req",
        )
        assert result.source_format == "docx"
        assert adapter.called_with["fmt"] == "docx"

    @pytest.mark.asyncio
    async def test_invalid_extension_rejected(self):
        with pytest.raises(InvalidDocumentError):
            await _use_case().execute(
                file_bytes=b"x", filename="scan.hwp", owner_user_id="7",
                mcp_pdf_to_html_tool_id=None, mcp_html_to_doc_tool_id=None,
                request_id="req",
            )

    @pytest.mark.asyncio
    async def test_oversize_rejected(self):
        uc = _use_case(max_file_mb=1)
        with pytest.raises(DocumentTooLargeError):
            await uc.execute(
                file_bytes=b"x" * (2 * 1024 * 1024), filename="a.pdf",
                owner_user_id="7",
                mcp_pdf_to_html_tool_id=None, mcp_html_to_doc_tool_id=None,
                request_id="req",
            )

    @pytest.mark.asyncio
    async def test_missing_mcp_tool_ids_rejected(self):
        uc = _use_case(
            default_pdf_to_html_tool_id="", default_html_to_doc_tool_id=""
        )
        with pytest.raises(McpToolNotConfiguredError):
            await uc.execute(
                file_bytes=b"x", filename="a.pdf", owner_user_id="7",
                mcp_pdf_to_html_tool_id=None, mcp_html_to_doc_tool_id=None,
                request_id="req",
            )


class TestPreviewHtml:
    """D1/D3/D9: PDF layout 미리보기 이원화 — 실패는 폴백, DOCX/off는 미호출."""

    async def _run(self, uc, filename="a.pdf"):
        return await uc.execute(
            file_bytes=b"x", filename=filename, owner_user_id="7",
            mcp_pdf_to_html_tool_id=None, mcp_html_to_doc_tool_id=None,
            request_id="req",
        )

    @pytest.mark.asyncio
    async def test_pdf_returns_layout_preview(self):
        adapter = FakeAdapter(preview_html="<div class='pdf-page'>p</div>")
        uc = _use_case(adapter=adapter, preview_dpi=120)
        result = await self._run(uc)
        assert result.preview_html == "<div class='pdf-page'>p</div>"
        preview_calls = [c for c in adapter.calls if c["options"] is not None]
        assert preview_calls == [
            dict(fmt="pdf", tool_id="mcp_default_p2h",
                 options={"mode": "layout", "dpi": 120}),
        ]

    @pytest.mark.asyncio
    async def test_docx_skips_preview(self):
        adapter = FakeAdapter()
        uc = _use_case(adapter=adapter)
        result = await self._run(uc, filename="양식.docx")
        assert result.preview_html is None
        assert all(c["options"] is None for c in adapter.calls)

    @pytest.mark.asyncio
    async def test_preview_failure_falls_back_to_none(self):
        adapter = FakeAdapter(preview_error=McpConversionError("layout down"))
        uc = _use_case(adapter=adapter)
        result = await self._run(uc)
        assert result.preview_html is None      # 전체 extract는 성공 (D3)
        assert result.html                       # text 경로는 정상
        uc._logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_preview_mode_off_skips(self):
        adapter = FakeAdapter()
        uc = _use_case(adapter=adapter, preview_mode="off")
        result = await self._run(uc)
        assert result.preview_html is None
        assert all(c["options"] is None for c in adapter.calls)

    @pytest.mark.asyncio
    async def test_preview_html_sanitized(self):
        adapter = FakeAdapter(
            preview_html="<div>ok</div><script>bad()</script>"
        )
        uc = _use_case(adapter=adapter)
        result = await self._run(uc)
        assert "<script" not in result.preview_html
        assert "<div>ok</div>" in result.preview_html
