"""PII 마스킹 포트 인터페이스 (도메인 경계).

- PiiDetectorPort: 텍스트에서 PII 위치를 탐지 (infrastructure에서 구현)
- PiiInspectPort: 값을 바꾸지 않고 PII 건수만 센다 (MCP 경계 검사가 의존)
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.pii_masking.schemas import PiiMatch, PiiType


@runtime_checkable
class PiiDetectorPort(Protocol):
    """텍스트 내 PII를 탐지하여 위치 목록을 반환한다."""

    def detect(self, text: str) -> list[PiiMatch]:
        ...


@runtime_checkable
class PiiInspectPort(Protocol):
    """Design Ref: §4.6 — MCP 호출·수신 시 타입별 건수만 얻는다. 값은 불변."""

    def inspect(self, value: object) -> dict[PiiType, int]:
        ...

    def find_orphan_argument(self, value: object) -> str | None:
        """도구로 보내면 안 되는 지어낸 placeholder. shadow 모드는 항상 None."""
        ...
