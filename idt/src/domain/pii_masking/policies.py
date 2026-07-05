"""PII 마스킹 도메인 정책: 탐지 우선순위, 오탐 저감 검증(Luhn, 주민번호 약식).

순수 규칙만 포함하며 외부 의존성을 갖지 않는다.
"""
from __future__ import annotations

from src.domain.pii_masking.schemas import PiiType

# 탐지 우선순위(겹침 시 상위 타입이 span 점유). 느슨한 ACCOUNT가 항상 마지막.
DETECTION_PRIORITY: tuple[PiiType, ...] = (
    PiiType.RRN,
    PiiType.CARD,
    PiiType.PHONE,
    PiiType.EMAIL,
    PiiType.ACCOUNT,
)

# 응답단 미매핑 PII redact 표기 접두.
REDACT_PREFIX = "REDACTED"


class PiiMaskingPolicy:
    """탐지 결과의 유효성 검증 규칙 모음."""

    @staticmethod
    def luhn_valid(number: str) -> bool:
        """Luhn 체크섬 통과 여부. 구분자는 제거 후 검사."""
        digits = [int(c) for c in number if c.isdigit()]
        if len(digits) < 13:
            return False
        checksum = 0
        # 오른쪽에서 두 번째부터 2배(odd index from right).
        for idx, digit in enumerate(reversed(digits)):
            if idx % 2 == 1:
                digit *= 2
                if digit > 9:
                    digit -= 9
            checksum += digit
        return checksum % 10 == 0

    @staticmethod
    def rrn_valid(rrn: str) -> bool:
        """주민등록번호 약식 검증: 13자리, 월/일 범위, 성별코드(1~8)."""
        digits = "".join(c for c in rrn if c.isdigit())
        if len(digits) != 13:
            return False
        month = int(digits[2:4])
        day = int(digits[4:6])
        gender = int(digits[6])
        if not 1 <= month <= 12:
            return False
        if not 1 <= day <= 31:
            return False
        return 1 <= gender <= 8

    @staticmethod
    def email_valid(email: str) -> bool:
        """이메일 약식 검증: TLD가 2자 이상 알파벳."""
        tld = email.rsplit(".", 1)[-1]
        return len(tld) >= 2 and tld.isalpha()

    @classmethod
    def is_valid(cls, pii_type: PiiType, value: str) -> bool:
        """타입별 유효성 검증. 검증 규칙이 없는 타입은 항상 True."""
        if pii_type is PiiType.RRN:
            return cls.rrn_valid(value)
        if pii_type is PiiType.CARD:
            return cls.luhn_valid(value)
        if pii_type is PiiType.EMAIL:
            return cls.email_valid(value)
        return True
