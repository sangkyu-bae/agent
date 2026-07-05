"""document_extractor 도메인 예외 (Design §3-1 에러 계약 매핑).

⚠️ 외부 의존 금지 — 순수 예외 계층만.
"""


class DocumentExtractorError(Exception):
    """document_extractor 도메인 공통 베이스."""


class InvalidDocumentError(DocumentExtractorError):
    """미허용 확장자 / 빈 파일 — 400 INVALID_DOCUMENT."""


class DocumentTooLargeError(DocumentExtractorError):
    """업로드 크기 초과 — 413 DOCUMENT_TOO_LARGE."""


class InvalidSlotError(DocumentExtractorError):
    """슬롯 개수/키 패턴/중복/타입 위반 — 400."""


class TemplateTokenMismatchError(DocumentExtractorError):
    """html_skeleton ↔ 슬롯 토큰 정합 실패 (D2) — 400."""


class RegenLimitExceededError(DocumentExtractorError):
    """재추천 상한(MAX_REGEN) 초과 (R5) — 429 REGEN_LIMIT_EXCEEDED."""


class McpToolNotConfiguredError(DocumentExtractorError):
    """변환 MCP 도구 미지정 + settings 폴백 부재 (D5) — 400 MCP_TOOL_NOT_CONFIGURED."""


class McpConversionError(DocumentExtractorError):
    """MCP 변환 도구 로드 실패/변환 실패 — 502 MCP_CONVERSION_FAILED."""


class SlotExtractionFailedError(DocumentExtractorError):
    """LLM 슬롯 추출 실패(재시도 후) — 502 SLOT_EXTRACTION_FAILED."""


class ComposeError(DocumentExtractorError):
    """런타임 합성 실패(LLM JSON 계약 위반 재시도 후 / 변환 실패) — 파일 미생성 (D6)."""
