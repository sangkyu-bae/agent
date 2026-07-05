"""PII 마스킹 포트 인터페이스 (도메인 경계).

- PiiDetectorPort: 텍스트에서 PII 위치를 탐지 (infrastructure에서 구현)
- PiiMaskingPort: 마스킹/복원 진입점 (application에서 구현, 부착 코드가 의존)
- TokenVaultStorePort: vault 영속화 교체 지점 (후속 plan용)
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.pii_masking.schemas import PiiMatch, TokenVault


@runtime_checkable
class PiiDetectorPort(Protocol):
    """텍스트 내 PII를 탐지하여 위치 목록을 반환한다."""

    def detect(self, text: str) -> list[PiiMatch]:
        ...


@runtime_checkable
class PiiMaskingPort(Protocol):
    """외부 LLM 경계에서의 마스킹/복원 진입점."""

    def mask(self, text: str, session_id: str) -> str:
        """입력/검색결과의 PII를 placeholder로 치환."""
        ...

    def unmask(self, text: str, session_id: str) -> str:
        """응답의 placeholder를 원복하고 미매핑 PII는 redact."""
        ...


@runtime_checkable
class TokenVaultStorePort(Protocol):
    """TokenVault 영속화 교체 지점 (인메모리 → Redis 등). 후속 plan."""

    def get(self, session_id: str) -> TokenVault:
        ...

    def clear(self, session_id: str) -> None:
        ...
