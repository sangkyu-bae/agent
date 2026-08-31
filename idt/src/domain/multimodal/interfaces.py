"""multimodal-extractor 포트.

Design Ref: multimodal-extractor §9.5 — Protocol 2개 + 설정 Repository.
AnalysisResult 는 pdf_analyzer 도메인 스키마(같은 domain 레이어)라 참조 허용.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from src.domain.multimodal.schemas import DescriptionDraft
from src.domain.multimodal.value_objects import (
    ElementType,
    ImageCandidate,
    MultimodalSettings,
)

if TYPE_CHECKING:
    from src.domain.pdf_analyzer.schemas import AnalysisResult


class ImageExtractorPort(Protocol):
    """파일 바이트 → 이미지 후보.

    레지스트리 키는 supported_extensions (소문자 확장자).
    """

    supported_extensions: frozenset[str]

    def extract(
        self,
        file_bytes: bytes,
        filename: str,
        analysis: "AnalysisResult | None",
    ) -> list[ImageCandidate]: ...


@dataclass(frozen=True)
class DescribeOptions:
    output_language: str
    detail_level: str


@dataclass(frozen=True)
class DescribeOutcome:
    draft: DescriptionDraft
    degraded_output_mode: bool
    output_mode: str  # strict | json | text
    # Plan FR-20: 응답 usage_metadata(input/output/total_tokens).
    # 모드·벤더에 따라 None 가능
    usage: dict[str, int] | None = None


class VisionDescriberPort(Protocol):
    """이미지 1장 → DescriptionDraft.

    레지스트리 키는 provider (LlmModel.provider 와 동일 문자열).
    """

    provider: str

    async def describe(
        self,
        image: ImageCandidate,
        element_type: ElementType,
        options: DescribeOptions,
    ) -> DescribeOutcome: ...


class MultimodalSettingRepository(Protocol):
    async def get(self, request_id: str) -> MultimodalSettings: ...

    async def update(
        self, settings: MultimodalSettings, request_id: str
    ) -> MultimodalSettings: ...
