"""ImageGenerationPolicy — image-generation-tool Design §3.1 (순수 규칙)."""
import secrets
from datetime import datetime

from src.domain.image_generation.exceptions import (
    ImageTurnCapExceededError,
    InvalidImageRequestError,
)
from src.domain.image_generation.value_objects import GenerationMode


class ImageGenerationPolicy:
    @staticmethod
    def validate_prompt(prompt: str, *, max_chars: int) -> str:
        """공백 정리 후 빈 값·길이 초과를 거부한다."""
        cleaned = (prompt or "").strip()
        if not cleaned:
            raise InvalidImageRequestError("이미지 생성 프롬프트가 비어 있습니다.")
        if len(cleaned) > max_chars:
            raise InvalidImageRequestError(
                f"이미지 생성 프롬프트가 너무 깁니다 ({len(cleaned)} > {max_chars}자)."
            )
        return cleaned

    @staticmethod
    def check_turn_cap(count: int, *, max_per_turn: int) -> None:
        """이번 턴 생성 건수가 상한에 도달했으면 거부 (FR-10)."""
        if count >= max_per_turn:
            raise ImageTurnCapExceededError(max_per_turn)

    @staticmethod
    def resolve_mode(
        requested: GenerationMode, *, has_attachment: bool
    ) -> tuple[GenerationMode, bool]:
        """(실효 모드, 폴백 여부). edit 인데 첨부가 없으면 generate 로 (D-08)."""
        if requested == GenerationMode.EDIT and not has_attachment:
            return GenerationMode.GENERATE, True
        return requested, False

    @staticmethod
    def sub_agent_cap(parent_cap: int) -> int:
        """서브 그래프 상한 = 부모의 절반, 하한 1 (D-09)."""
        return max(1, parent_cap // 2)

    @staticmethod
    def output_filename(now: datetime, *, mime: str = "image/png") -> str:
        """저장 파일명. 확장자는 실제 바이트의 mime 을 따른다 (모르면 png)."""
        ext = _EXT_BY_MIME.get(mime, ".png")
        return f"generated-{now.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}{ext}"


_EXT_BY_MIME = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
