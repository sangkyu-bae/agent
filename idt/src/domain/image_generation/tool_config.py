"""ImageGenerationToolConfig — 에이전트별 이미지 생성 도구 설정 VO (Design §3.1).

DocumentExtractorToolConfig 패턴(frozen dataclass + __post_init__ 검증).
WorkerDefinition.tool_config(dict)에 asdict 형태로 저장된다.
"""
from dataclasses import asdict, dataclass

from src.domain.image_generation.value_objects import ImageQuality, ImageSize

_SIZES = {s.value for s in ImageSize}
_QUALITIES = {q.value for q in ImageQuality}


@dataclass(frozen=True)
class ImageGenerationToolConfig:
    llm_model_id: str
    default_size: str = ImageSize.SQUARE_1024.value
    quality: str = ImageQuality.STANDARD.value

    def __post_init__(self) -> None:
        if not self.llm_model_id:
            raise ValueError("llm_model_id is required")
        if self.default_size not in _SIZES:
            raise ValueError(
                f"default_size must be one of {sorted(_SIZES)}, "
                f"got {self.default_size!r}"
            )
        if self.quality not in _QUALITIES:
            raise ValueError(
                f"quality must be one of {sorted(_QUALITIES)}, got {self.quality!r}"
            )

    def model_dump(self) -> dict:
        return asdict(self)
