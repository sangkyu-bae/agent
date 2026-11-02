"""ImageGeneratorPort — provider 어댑터 계약 (Design §3.1). infrastructure 가 구현."""
from typing import Protocol

from src.domain.image_generation.value_objects import (
    ImageBytes,
    ImageQuality,
    ImageSize,
)


class ImageGeneratorPort(Protocol):
    provider: str

    async def generate(
        self, *, prompt: str, size: ImageSize, quality: ImageQuality
    ) -> ImageBytes:
        """텍스트 → 이미지 1장. 실패는 ImageProviderError."""
        ...

    async def edit(
        self, *, prompt: str, source: bytes, source_mime: str, size: ImageSize
    ) -> ImageBytes:
        """첨부 이미지 + 프롬프트 → 편집 이미지 1장."""
        ...
