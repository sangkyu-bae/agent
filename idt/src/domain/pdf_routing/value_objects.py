from dataclasses import dataclass, field
from typing import Dict


DEFAULT_ROUTING_MAP: Dict[str, str] = {
    "text_heavy": "pymupdf",
    "ocr_heavy": "llamaparser",
    "table_heavy": "pymupdf4llm",
    "multimodal": "llamaparser",
}

DEFAULT_FALLBACK_PARSER: str = "pymupdf"
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.5


@dataclass(frozen=True)
class ParserRoutingConfig:
    routing_map: Dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_ROUTING_MAP)
    )
    fallback_parser: str = DEFAULT_FALLBACK_PARSER
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence_threshold <= 1.0):
            raise ValueError(
                "confidence_threshold must be between 0.0 and 1.0"
            )
        if not self.fallback_parser or not self.fallback_parser.strip():
            raise ValueError("fallback_parser cannot be empty")
        if not isinstance(self.routing_map, dict):
            raise ValueError("routing_map must be a dict")
