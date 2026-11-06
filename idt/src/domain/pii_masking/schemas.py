"""PII 마스킹 도메인 스키마: PiiType, PiiMatch, TokenVault, PiiRunScope.

가역 마스킹 핵심: TokenVault가 placeholder↔원본을 양방향으로 보관하며,
동일 원본값은 동일 placeholder로 매핑하여 LLM 추론 일관성을 보장한다.

Design Ref: pii-masking-integration §3 — vault는 런 범위 지역 객체다. 저장·로깅하지
않는다. 원본은 이미 대화 이력에 있고 매 호출마다 전체 메시지를 다시 마스킹하므로
런을 넘겨 보관할 이유가 없다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, StrEnum


class PiiType(str, Enum):
    """탐지/마스킹 대상 PII 종류."""

    RRN = "rrn"          # 주민등록번호
    PHONE = "phone"      # 휴대폰/전화번호
    EMAIL = "email"      # 이메일
    CARD = "card"        # 신용/체크카드 (자릿수 + Luhn)
    ACCOUNT = "account"  # 한국 은행 계좌 (휴리스틱)


class PiiMaskingMode(StrEnum):
    """SHADOW는 탐지·기록만 하고 LLM 요청을 바꾸지 않는다."""

    SHADOW = "shadow"
    ON = "on"


# placeholder 표기. 대소문자 변형은 원복 대상이다 (Design §3.3).
PLACEHOLDER_PATTERN = re.compile(
    r"\[(" + "|".join(t.value.upper() for t in PiiType) + r")_(\d+)\]",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PiiMatch:
    """텍스트에서 탐지된 단일 PII 위치 Value Object."""

    pii_type: PiiType
    text: str
    start: int
    end: int


@dataclass
class TokenVault:
    """런 범위 placeholder↔원본 양방향 매핑.

    - get_or_create_placeholder: 동일 원본 → 동일 placeholder 보장
    - restore: 응답 텍스트의 placeholder를 원본으로 역치환
    - reserve_literals: 입력에 원래 있던 placeholder 형태 문자열과의 충돌 방지

    await가 없는 동기 코드이므로 같은 이벤트 루프의 병렬 워커가 공유해도 경합이 없다.
    """

    _by_placeholder: dict[str, str] = field(default_factory=dict)
    _by_original: dict[str, str] = field(default_factory=dict)
    _counters: dict[PiiType, int] = field(default_factory=dict)
    _unique: dict[PiiType, int] = field(default_factory=dict)
    _literals: set[str] = field(default_factory=set)

    def get_or_create_placeholder(self, pii_type: PiiType, original: str) -> str:
        """원본값에 대응하는 placeholder를 반환(없으면 생성)."""
        if original in self._by_original:
            return self._by_original[original]
        self._counters[pii_type] = self._counters.get(pii_type, 0) + 1
        self._unique[pii_type] = self._unique.get(pii_type, 0) + 1
        placeholder = f"[{pii_type.value.upper()}_{self._counters[pii_type]}]"
        self._by_placeholder[placeholder] = original
        self._by_original[original] = placeholder
        return placeholder

    def reserve_literals(self, text: str) -> None:
        """text에 이미 있는 placeholder 형태 문자열의 번호를 건너뛰도록 예약한다."""
        for match in PLACEHOLDER_PATTERN.finditer(text):
            key = match.group(0).upper()
            if key in self._by_placeholder:
                continue
            pii_type = PiiType(match.group(1).lower())
            number = int(match.group(2))
            self._counters[pii_type] = max(self._counters.get(pii_type, 0), number)
            self._literals.add(key)

    def restore(self, text: str) -> str:
        """text 내 placeholder를 모두 원본으로 복원. 모르는 표기는 그대로 둔다."""
        return PLACEHOLDER_PATTERN.sub(
            lambda m: self._by_placeholder.get(m.group(0).upper(), m.group(0)), text
        )

    def is_orphan(self, placeholder: str) -> bool:
        """vault에 없고 입력 문자열로 예약되지도 않은 placeholder면 True."""
        key = placeholder.upper()
        return key not in self._by_placeholder and key not in self._literals

    def counts(self) -> dict[PiiType, int]:
        """타입별 고유 값 개수. 관측은 값 대신 이 건수만 쓴다."""
        return dict(self._unique)

    @property
    def size(self) -> int:
        """보관 중인 매핑 수 (로깅 시 값 대신 개수만 노출)."""
        return len(self._by_placeholder)


@dataclass
class PiiRunScope:
    """런 1개의 마스킹 범위. 지역 객체로만 전달한다 (Design §7)."""

    mode: PiiMaskingMode
    vault: TokenVault = field(default_factory=TokenVault)
