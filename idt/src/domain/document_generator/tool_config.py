"""DocumentGeneratorToolConfig: 문서생성기 도구 설정 VO (doc-generator Design §4-2).

DocumentExtractorToolConfig 패턴(frozen dataclass + __post_init__ 검증).
WorkerDefinition.tool_config(dict)에 asdict 형태로 저장된다.
"""
from dataclasses import asdict, dataclass

_VALID_OUTPUT_FORMATS = {"pdf", "docx"}


@dataclass(frozen=True)
class DocumentGeneratorToolConfig:
    """에이전트별 문서생성기 설정.

    - type_id: 그 에이전트·그 도구 전용 문서 유형 (공유 없음)
    - mcp_html_to_doc_tool_id: 변환 MCP 도구. 빈 값 허용 —
      런타임에 settings 폴백 체인으로 해석 (D5)
    - output_format: 유형별 빌드타임 설정 (기본 docx — D4)
    """

    type_id: str
    mcp_html_to_doc_tool_id: str
    output_format: str

    def __post_init__(self) -> None:
        if not self.type_id:
            raise ValueError("type_id is required")
        if self.mcp_html_to_doc_tool_id and not self.mcp_html_to_doc_tool_id.startswith(
            "mcp_"
        ):
            raise ValueError(
                "mcp_html_to_doc_tool_id must start with 'mcp_' or be empty, "
                f"got {self.mcp_html_to_doc_tool_id!r}"
            )
        if self.output_format not in _VALID_OUTPUT_FORMATS:
            raise ValueError(
                f"output_format must be one of {sorted(_VALID_OUTPUT_FORMATS)}, "
                f"got {self.output_format!r}"
            )

    def model_dump(self) -> dict:
        """WorkerDefinition.tool_config 저장용 dict."""
        return asdict(self)
