"""PII 마스킹 애플리케이션 설정 DTO."""
from __future__ import annotations

from dataclasses import dataclass

from src.domain.pii_masking.schemas import PiiMaskingMode, PiiType


@dataclass(frozen=True)
class PiiMaskingConfig:
    """마스킹 동작 설정 (config.Settings에서 생성).

    전역 해제는 여기 없다. PII_MASKING_ENABLED=false면 서비스 자체를 조립하지
    않는다 (Design D-03). 소비 지점: api/main.py get_pii_masker().
    """

    mode: PiiMaskingMode
    enabled_types: frozenset[PiiType]

    @classmethod
    def from_settings(cls, *, mode: str, types_csv: str) -> PiiMaskingConfig:
        """설정 문자열을 파싱한다.

        Design D-02: 오타는 예외로 올린다. 무시하면 특정 타입의 보호가 조용히
        꺼진다(prompt guard G-10과 같은 함정).
        """
        tokens = [t.strip().lower() for t in types_csv.split(",") if t.strip()]
        if not tokens:
            raise ValueError("PII_MASKING_TYPES is empty")
        return cls(
            mode=PiiMaskingMode(mode),
            enabled_types=frozenset(PiiType(t) for t in tokens),
        )
