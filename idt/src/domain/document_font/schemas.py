"""폰트 임베드 값 객체 (Design §3.1).

DB 스키마 변경 없음 — 프로세스 내부 전달 계약만 정의한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmbeddedFont:
    """서브셋된 폰트 1종 (weight 단위)."""

    family: str
    weight: int
    data_uri: str
    byte_size: int
    missing_chars: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class FontEmbedResult:
    """wrap() 결과.

    applied=False 면 원본 HTML 을 그대로 돌려준 것이며, 호출자는 변환을
    중단하지 않는다 (Plan FR-09 — 폰트 실패가 문서 생성을 막지 않는다).
    """

    html: str
    fonts: tuple[EmbeddedFont, ...] = field(default=())
    applied: bool = False
    reason: str = ""

    @property
    def font_bytes(self) -> int:
        """서브셋 폰트 원본(TTF) 바이트 합."""
        return sum(font.byte_size for font in self.fonts)

    @property
    def embedded_bytes(self) -> int:
        """HTML 에 실제로 실리는 base64 바이트 합 — 페이로드 예산의 기준."""
        return sum(len(font.data_uri) for font in self.fonts)

    @property
    def missing_chars(self) -> tuple[str, ...]:
        seen: list[str] = []
        for font in self.fonts:
            for char in font.missing_chars:
                if char not in seen:
                    seen.append(char)
        return tuple(seen)
