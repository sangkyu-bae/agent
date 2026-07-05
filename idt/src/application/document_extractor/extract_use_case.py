"""ExtractDocumentUseCase: 업로드 → MCP 변환 → 슬롯 추천 (Design §3-2, GA2).

stateless — 서버 영속 상태 없음(원본은 attachment store 임시 저장만, D3 1단계).
workflow_compiler 미경유 (Plan 확정 2).
"""
from src.application.document_extractor.schemas import (
    ExtractResponse,
    TemplateSlotDto,
)
from src.domain.agent_attachment.value_objects import AttachmentType
from src.domain.document_extractor.exceptions import (
    McpConversionError,
    McpToolNotConfiguredError,
)
from src.domain.document_extractor.policies import (
    DocumentFilePolicy,
    HtmlSanitizePolicy,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ExtractDocumentUseCase:
    def __init__(
        self,
        attachment_store,
        conversion_adapter,
        slot_extractor,
        logger: LoggerInterface,
        max_file_mb: int,
        default_pdf_to_html_tool_id: str = "",
        default_html_to_doc_tool_id: str = "",
        preview_mode: str = "layout",
        preview_dpi: int = 120,
    ) -> None:
        self._store = attachment_store
        self._adapter = conversion_adapter
        self._extractor = slot_extractor
        self._logger = logger
        self._max_file_mb = max_file_mb
        self._default_p2h = default_pdf_to_html_tool_id
        self._default_h2d = default_html_to_doc_tool_id
        self._preview_mode = preview_mode
        self._preview_dpi = preview_dpi

    async def execute(
        self,
        file_bytes: bytes,
        filename: str,
        owner_user_id: str,
        mcp_pdf_to_html_tool_id: str | None,
        mcp_html_to_doc_tool_id: str | None,
        request_id: str,
    ) -> ExtractResponse:
        self._logger.info(
            "ExtractDocumentUseCase start",
            request_id=request_id,
            filename=filename,
            size=len(file_bytes),
        )
        try:
            source_format = DocumentFilePolicy.validate(
                filename, len(file_bytes), self._max_file_mb
            )
            p2h, h2d = self._resolve_mcp_ids(
                mcp_pdf_to_html_tool_id, mcp_html_to_doc_tool_id
            )

            stored = self._store.save(
                file_bytes=file_bytes,
                filename=filename,
                attachment_type=AttachmentType.DOCUMENT,
                owner_user_id=owner_user_id,
            )

            raw_html = await self._adapter.to_html(
                file_bytes, source_format, p2h, request_id
            )
            html = HtmlSanitizePolicy.clean(raw_html)

            suggested = await self._extractor.extract(html, request_id)

            preview_html = await self._maybe_preview_html(
                file_bytes, source_format, p2h, request_id
            )

            self._logger.info(
                "ExtractDocumentUseCase done",
                request_id=request_id,
                source_file_id=stored.file_id,
                slot_count=len(suggested.slots),
                has_preview=preview_html is not None,
            )
            return ExtractResponse(
                source_file_id=stored.file_id,
                source_format=source_format,
                html=html,
                preview_html=preview_html,
                suggested_slots=[
                    TemplateSlotDto.from_domain(s) for s in suggested.slots
                ],
                mcp_pdf_to_html_tool_id=p2h,
                mcp_html_to_doc_tool_id=h2d,
            )
        except Exception as e:
            self._logger.error(
                "ExtractDocumentUseCase failed", exception=e, request_id=request_id
            )
            raise

    async def _maybe_preview_html(
        self,
        file_bytes: bytes,
        source_format: str,
        p2h: str,
        request_id: str,
    ) -> str | None:
        """PDF만 layout 미리보기 변환 (D1). 실패는 None 폴백 (D3).

        DOCX는 soffice 변환(text 경로)이 이미 시각 충실 → 미변환.
        """
        if source_format != "pdf" or self._preview_mode != "layout":
            return None
        try:
            raw = await self._adapter.to_html(
                file_bytes,
                source_format,
                p2h,
                request_id,
                options={"mode": "layout", "dpi": self._preview_dpi},
            )
        except McpConversionError as e:
            self._logger.warning(
                "preview conversion failed, fallback to text html",
                request_id=request_id,
                error=str(e),
            )
            return None
        return HtmlSanitizePolicy.clean(raw)

    def _resolve_mcp_ids(
        self, p2h: str | None, h2d: str | None
    ) -> tuple[str, str]:
        """명시 지정 우선, 미지정 시 settings 폴백. 둘 다 없으면 에러 (D5)."""
        effective_p2h = p2h or self._default_p2h
        effective_h2d = h2d or self._default_h2d
        if not effective_p2h:
            raise McpToolNotConfiguredError(
                "pdf/doc→html 변환 MCP 도구가 지정되지 않았습니다. "
                "요청에 mcp_pdf_to_html_tool_id를 지정하거나 "
                "DOCUMENT_EXTRACTOR_PDF_TO_HTML_TOOL_ID 설정을 등록하세요."
            )
        if not effective_h2d:
            raise McpToolNotConfiguredError(
                "html→pdf/doc 변환 MCP 도구가 지정되지 않았습니다. "
                "요청에 mcp_html_to_doc_tool_id를 지정하거나 "
                "DOCUMENT_EXTRACTOR_HTML_TO_DOC_TOOL_ID 설정을 등록하세요."
            )
        return effective_p2h, effective_h2d
