"""PresentationGeneratorToolConfig — presentation_generator 워커 tool_config VO.

Design Ref: golden-sample-blueprint §9.1 / D7 — DocumentGeneratorToolConfig 동형
(frozen dataclass + __post_init__ 검증). WorkerDefinition.tool_config(dict)에
asdict 형태로 저장된다. blueprint_id 는 전역 document_blueprint.id 소프트 참조.
"""

from dataclasses import dataclass

_VALID_OUTPUT_FORMATS = {"pptx", "pdf"}
MAX_SLIDES_LIMIT = 60
DEFAULT_MAX_SLIDES = 15


@dataclass(frozen=True)
class PresentationGeneratorToolConfig:
    blueprint_id: str
    output_format: str = "pptx"
    mcp_pptx_to_pdf_tool_id: str = ""
    max_slides: int = DEFAULT_MAX_SLIDES

    def __post_init__(self) -> None:
        if not self.blueprint_id:
            raise ValueError("blueprint_id is required")
        if self.output_format not in _VALID_OUTPUT_FORMATS:
            raise ValueError(
                f"output_format must be one of {sorted(_VALID_OUTPUT_FORMATS)}, "
                f"got {self.output_format!r}"
            )
        if self.mcp_pptx_to_pdf_tool_id and not self.mcp_pptx_to_pdf_tool_id.startswith(
            "mcp_"
        ):
            raise ValueError(
                "mcp_pptx_to_pdf_tool_id must start with 'mcp_' or be empty, "
                f"got {self.mcp_pptx_to_pdf_tool_id!r}"
            )
        if not 1 <= self.max_slides <= MAX_SLIDES_LIMIT:
            raise ValueError(f"max_slides must be within 1..{MAX_SLIDES_LIMIT}")
