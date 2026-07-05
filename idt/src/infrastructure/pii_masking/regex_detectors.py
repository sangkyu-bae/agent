"""정규식 기반 PII Detector 구현 (PiiDetectorPort).

우선순위(DETECTION_PRIORITY)대로 탐지하며, 이미 점유된 span과 겹치는 매칭은 건너뛴다.
타입별 오탐 저감은 PiiMaskingPolicy.is_valid에 위임한다.
"""
from __future__ import annotations

import re

from src.domain.pii_masking.patterns import (
    ACCOUNT_PATTERN,
    CARD_PATTERN,
    EMAIL_PATTERN,
    LANDLINE_PATTERN,
    MOBILE_PATTERN,
    RRN_PATTERN,
)
from src.domain.pii_masking.policies import DETECTION_PRIORITY, PiiMaskingPolicy
from src.domain.pii_masking.schemas import PiiMatch, PiiType

# 타입별 적용 패턴 목록.
_PATTERNS: dict[PiiType, list[re.Pattern[str]]] = {
    PiiType.RRN: [RRN_PATTERN],
    PiiType.CARD: [CARD_PATTERN],
    PiiType.PHONE: [MOBILE_PATTERN, LANDLINE_PATTERN],
    PiiType.EMAIL: [EMAIL_PATTERN],
    PiiType.ACCOUNT: [ACCOUNT_PATTERN],
}


class RegexPiiDetector:
    """정규식 + 정책 검증 기반 PII 탐지기."""

    def __init__(self, policy: PiiMaskingPolicy | None = None) -> None:
        self._policy = policy or PiiMaskingPolicy()

    def detect(self, text: str) -> list[PiiMatch]:
        """우선순위 순으로 비중첩 PiiMatch 목록을 반환(start 오름차순)."""
        occupied: list[tuple[int, int]] = []
        results: list[PiiMatch] = []
        for pii_type in DETECTION_PRIORITY:
            for pattern in _PATTERNS[pii_type]:
                for match in pattern.finditer(text):
                    span = (match.start(), match.end())
                    if self._overlaps(span, occupied):
                        continue
                    value = match.group()
                    if not self._policy.is_valid(pii_type, value):
                        continue
                    occupied.append(span)
                    results.append(
                        PiiMatch(
                            pii_type=pii_type,
                            text=value,
                            start=span[0],
                            end=span[1],
                        )
                    )
        results.sort(key=lambda m: m.start)
        return results

    @staticmethod
    def _overlaps(span: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
        """span이 기존 점유 구간과 겹치면 True."""
        start, end = span
        return any(start < o_end and o_start < end for o_start, o_end in occupied)
