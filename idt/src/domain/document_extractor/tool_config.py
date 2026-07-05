"""DocumentExtractorToolConfig: 문서추출기 도구 설정 VO (Design §2-3).

RagToolConfig 패턴(frozen dataclass + __post_init__ 검증).
WorkerDefinition.tool_config(dict)에 asdict 형태로 저장된다.
"""
from dataclasses import asdict, dataclass

_VALID_OUTPUT_FORMATS = {"pdf", "docx"}


@dataclass(frozen=True)
class DocumentExtractorToolConfig:
    """에이전트별 문서추출기 설정.

    - template_id: 그 에이전트·그 도구 전용 템플릿 (공유 없음)
    - mcp_*_tool_id: 변환 MCP 도구 명시 저장 (Plan 결정 3)
    - output_format: 원본 업로드 포맷 따름 (Plan 결정 4)
    """

    template_id: str
    mcp_pdf_to_html_tool_id: str
    mcp_html_to_doc_tool_id: str
    output_format: str

    def __post_init__(self) -> None:
        if not self.template_id:
            raise ValueError("template_id is required")
        for name in ("mcp_pdf_to_html_tool_id", "mcp_html_to_doc_tool_id"):
            value = getattr(self, name)
            if not value or not value.startswith("mcp_"):
                raise ValueError(f"{name} must start with 'mcp_', got {value!r}")
        if self.output_format not in _VALID_OUTPUT_FORMATS:
            raise ValueError(
                f"output_format must be one of {sorted(_VALID_OUTPUT_FORMATS)}, "
                f"got {self.output_format!r}"
            )

    def model_dump(self) -> dict:
        """WorkerDefinition.tool_config 저장용 dict."""
        return asdict(self)
