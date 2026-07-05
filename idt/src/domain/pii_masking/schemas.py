"""PII 마스킹 도메인 스키마: PiiType, PiiMatch, MaskingResult, TokenVault.

가역 마스킹 핵심: TokenVault가 placeholder↔원본을 양방향으로 보관하며,
동일 원본값은 동일 placeholder로 매핑하여 LLM 추론 일관성을 보장한다.
TokenVault 값은 메모리 범위로만 다루고 영속/로깅하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PiiType(str, Enum):
    """탐지/마스킹 대상 PII 종류."""

    RRN = "rrn"          # 주민등록번호
    PHONE = "phone"      # 휴대폰/전화번호
    EMAIL = "email"      # 이메일
    CARD = "card"        # 신용/체크카드 (자릿수 + Luhn)
    ACCOUNT = "account"  # 한국 은행 계좌 (휴리스틱)


@dataclass(frozen=True)
class PiiMatch:
    """텍스트에서 탐지된 단일 PII 위치 Value Object."""

    pii_type: PiiType
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class MaskingResult:
    """단일 mask() 호출 결과 Value Object."""

    masked_text: str
    placeholders: dict[str, str]  # {placeholder: original} — 이번 호출에서 생성분


@dataclass
class TokenVault:
    """session 범위 placeholder↔원본 양방향 매핑.

    - get_or_create_placeholder: 동일 원본 → 동일 placeholder 보장
    - restore: 응답 텍스트의 placeholder를 원본으로 역치환
    """

    _by_placeholder: dict[str, str] = field(default_factory=dict)
    _by_original: dict[str, str] = field(default_factory=dict)
    _counters: dict[PiiType, int] = field(default_factory=dict)

    def get_or_create_placeholder(self, pii_type: PiiType, original: str) -> str:
        """원본값에 대응하는 placeholder를 반환(없으면 생성)."""
        if original in self._by_original:
            return self._by_original[original]
        self._counters[pii_type] = self._counters.get(pii_type, 0) + 1
        placeholder = f"[{pii_type.value.upper()}_{self._counters[pii_type]}]"
        self._by_placeholder[placeholder] = original
        self._by_original[original] = placeholder
        return placeholder

    def restore(self, text: str) -> str:
        """text 내 placeholder를 모두 원본으로 복원."""
        result = text
        for placeholder, original in self._by_placeholder.items():
            result = result.replace(placeholder, original)
        return result

    @property
    def size(self) -> int:
        """보관 중인 매핑 수 (로깅 시 값 대신 개수만 노출)."""
        return len(self._by_placeholder)


class TokenVaultRegistry:
    """session_id → TokenVault 인메모리 레지스트리.

    멀티턴 동일 PII 일관성을 위해 session_id 단위로 vault를 유지한다.
    영속화가 필요하면 TokenVaultStorePort 구현체로 교체한다(후속).
    """

    def __init__(self) -> None:
        self._vaults: dict[str, TokenVault] = {}

    def get(self, session_id: str) -> TokenVault:
        """session_id에 대응하는 vault 반환(없으면 생성)."""
        if session_id not in self._vaults:
            self._vaults[session_id] = TokenVault()
        return self._vaults[session_id]

    def clear(self, session_id: str) -> None:
        """세션 종료 시 vault 폐기(메모리 정리)."""
        self._vaults.pop(session_id, None)
