"""PII 마스킹 애플리케이션 설정 DTO."""
from __future__ import annotations

from dataclasses import dataclass

from src.domain.pii_masking.schemas import PiiType


@dataclass(frozen=True)
class PiiMaskingConfig:
    """마스킹 동작 설정 (config.Settings에서 생성)."""

    enabled: bool
    enabled_types: frozenset[PiiType]
    output_redact: bool

    @classmethod
    def from_settings(
        cls, *, enabled: bool, types_csv: str, output_redact: bool
    ) -> PiiMaskingConfig:
        """쉼표 구분 타입 문자열을 PiiType 집합으로 파싱."""
        parsed: set[PiiType] = set()
        for raw in types_csv.split(","):
            token = raw.strip().lower()
            if not token:
                continue
            try:
                parsed.add(PiiType(token))
            except ValueError:
                # 알 수 없는 타입은 무시(설정 오타가 전체를 깨뜨리지 않도록).
                continue
        return cls(
            enabled=enabled,
            enabled_types=frozenset(parsed),
            output_redact=output_redact,
        )
