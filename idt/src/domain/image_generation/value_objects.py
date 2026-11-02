"""image_generation 값 객체 — image-generation-tool Design §3.1.

외부 의존(SDK·PIL·LangChain) 금지. provider 공통 프리셋만 다루고
provider 파라미터 번역은 infrastructure 어댑터가 맡는다 (D-07).
"""
from dataclasses import dataclass
from enum import StrEnum


class ImageSize(StrEnum):
    SQUARE_1024 = "1024x1024"
    LANDSCAPE_1536 = "1536x1024"
    PORTRAIT_1536 = "1024x1536"


class ImageQuality(StrEnum):
    STANDARD = "standard"
    HD = "hd"


class GenerationMode(StrEnum):
    GENERATE = "generate"
    EDIT = "edit"


@dataclass(frozen=True)
class SourceImage:
    """편집 입력 — 이번 턴 첨부 이미지(저장소 경로). 바이트는 유스케이스가 읽는다."""

    file_path: str
    mime: str
    file_name: str


@dataclass(frozen=True)
class ImageBytes:
    """어댑터 반환값 — 생성 결과 바이트와 치수."""

    data: bytes
    width: int
    height: int
    mime: str


@dataclass(frozen=True)
class GenerateImageCommand:
    prompt: str
    size: ImageSize
    quality: ImageQuality
    mode: GenerationMode
    source_image: SourceImage | None
    owner_user_id: str
    request_id: str
    # edit 요청인데 첨부가 없어 generate 로 폴백한 경우 (노드가 resolve_mode 로 결정)
    fell_back_to_generate: bool = False


@dataclass(frozen=True)
class GeneratedImage:
    """결과 — 바이트 없음(저장소 file_id 만). 상태·메시지·원장에 그대로 실어도 안전."""

    file_id: str
    filename: str
    width: int
    height: int
    mime: str
    model_id: str
    model_name: str
    provider: str
    prompt: str
    mode: GenerationMode
    elapsed_ms: int
    fell_back_to_generate: bool

    def to_state_dict(self) -> dict:
        """SupervisorState.generated_images 항목 (Design §3.2)."""
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "mime": self.mime,
            "width": self.width,
            "height": self.height,
            "prompt": self.prompt,
            "mode": self.mode.value,
        }
