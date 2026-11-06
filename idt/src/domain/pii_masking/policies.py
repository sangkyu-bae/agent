"""PII 마스킹 도메인 정책: 탐지 우선순위, 오탐 저감 검증(Luhn, 주민번호 약식).

순수 규칙만 포함하며 외부 의존성을 갖지 않는다.
"""
from __future__ import annotations

import re

from src.domain.pii_masking.patterns import BUSINESS_NUMBER_FORMAT
from src.domain.pii_masking.schemas import PLACEHOLDER_PATTERN, PiiRunScope, PiiType

# 스트림에서 보류할 수 있는 최대 꼬리 길이. `[ACCOUNT_9999]`보다 넉넉하다.
_STREAM_HOLD_MAX = 24
_TYPE_NAMES: tuple[str, ...] = tuple(t.value.upper() for t in PiiType)
_PREFIX_SHAPE = re.compile(r"\[([A-Za-z]*)(?:(_)(\d*))?")

# 사업자등록번호 체크섬 가중치(앞 9자리).
_BUSINESS_NUMBER_WEIGHTS: tuple[int, ...] = (1, 3, 7, 1, 3, 7, 1, 3, 5)
# 한국 은행 계좌 총 자릿수 범위. 8자리 날짜(2026-11-02)가 여기서 걸러진다.
_ACCOUNT_DIGITS_MIN = 10
_ACCOUNT_DIGITS_MAX = 14

# 탐지 우선순위(겹침 시 상위 타입이 span 점유). 느슨한 ACCOUNT가 항상 마지막.
DETECTION_PRIORITY: tuple[PiiType, ...] = (
    PiiType.RRN,
    PiiType.CARD,
    PiiType.PHONE,
    PiiType.EMAIL,
    PiiType.ACCOUNT,
)

# 원복되지 않은 고아 placeholder의 대체 표기 접두.
REDACT_PREFIX = "REDACTED"


class PlaceholderStreamPolicy:
    """Design Ref: §4.5 — 토큰 스트림에서 placeholder가 청크 경계에 걸렸는지 판정.

    스파이크에서 `[PHONE_1]`이 `[PH`, `ONE`, `_1]`로 나뉘어 흘렀다. 끝부분이
    placeholder 접두면 그 위치부터 보류해야 사용자에게 조각이 보이지 않는다.
    """

    @staticmethod
    def hold_start(text: str) -> int | None:
        """끝부분이 미완성 placeholder 접두면 그 `[` 위치, 아니면 None."""
        start = text.rfind("[")
        if start < 0 or len(text) - start > _STREAM_HOLD_MAX:
            return None
        match = _PREFIX_SHAPE.fullmatch(text[start:])
        if match is None:
            return None
        name, underscore = match.group(1).upper(), match.group(2)
        if underscore:
            return start if name in _TYPE_NAMES else None
        return start if any(t.startswith(name) for t in _TYPE_NAMES) else None


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

    @staticmethod
    def business_number_valid(value: str) -> bool:
        """사업자등록번호 여부: 3-2-5 표기 + 체크섬. 개인정보가 아니라 제외 대상이다."""
        if not BUSINESS_NUMBER_FORMAT.fullmatch(value):
            return False
        digits = [int(c) for c in value if c.isdigit()]
        total = sum(d * w for d, w in zip(digits, _BUSINESS_NUMBER_WEIGHTS))
        total += digits[8] * 5 // 10
        return (10 - total % 10) % 10 == digits[9]

    @classmethod
    def account_valid(cls, value: str) -> bool:
        """계좌 약식 검증: 총 10~14자리이고 사업자등록번호가 아니어야 한다."""
        count = sum(c.isdigit() for c in value)
        if not _ACCOUNT_DIGITS_MIN <= count <= _ACCOUNT_DIGITS_MAX:
            return False
        return not cls.business_number_valid(value)

    @classmethod
    def is_valid(cls, pii_type: PiiType, value: str) -> bool:
        """타입별 유효성 검증. 검증 규칙이 없는 타입은 항상 True."""
        if pii_type is PiiType.RRN:
            return cls.rrn_valid(value)
        if pii_type is PiiType.CARD:
            return cls.luhn_valid(value)
        if pii_type is PiiType.EMAIL:
            return cls.email_valid(value)
        if pii_type is PiiType.ACCOUNT:
            return cls.account_valid(value)
        return True


# 지어낸 placeholder를 인자로 쓴 도구 호출에 돌려주는 안내. 예시 placeholder를 넣지
# 않는다 — 다음 호출에서 입력 문자열로 예약되어 번호 체계를 흐린다.
PII_ORPHAN_TOOL_ARG_NOTICE = (
    "도구 인자에 대화에 없던 개인정보 자리표시자가 있어 실행하지 않았다. "
    "대화에 나온 자리표시자를 그대로 쓰거나, 값을 모르면 사용자에게 다시 물어보라."
)


# Check G-13 — 마스킹된 요청의 system 끝에 붙인다. 없으면 "확인된 값만 써라" 규칙을
# 가진 인자 작성 LLM 이 placeholder 를 미확인 값으로 보고 도구 호출을 포기한다.
# 번호 있는 예시는 넣지 않는다 (위 안내와 같은 이유).
PII_PLACEHOLDER_NOTICE = (
    "[개인정보 자리표시자 안내]\n"
    "대화의 대괄호 표기(예: 이메일·전화번호 자리에 들어간 '[EMAIL_번호]' 형태)는 "
    "시스템이 실제로 확인된 개인정보를 가린 자리표시자다. "
    "실제 값이 확인된 것으로 다루고, 도구 인자와 답변에는 대괄호까지 그대로 적어라. "
    "실행 직전에 원래 값으로 바뀐다. "
    "자리표시자라는 이유로 값을 미확인으로 판단하거나 다른 값을 지어내지 마라."
)


class PiiToolArgumentPolicy:
    """Design Ref: §4.6, D-08 — 도구로 나가기 직전 인자의 고아 placeholder 판정.

    알려진 placeholder는 이미 원복되어 있으므로, 이 시점에 남은 `[TYPE_n]`은
    LLM이 지어낸 값이다. vault 없이 형태만으로 판정한다.
    """

    @classmethod
    def find_orphan(cls, value: object) -> str | None:
        """처음 발견한 placeholder 문자열, 없으면 None. 키는 검사하지 않는다."""
        if isinstance(value, str):
            match = PLACEHOLDER_PATTERN.search(value)
            return match.group(0) if match else None
        if isinstance(value, dict):
            return cls._first(value.values())
        if isinstance(value, (list, tuple, set)):
            return cls._first(value)
        return None

    @classmethod
    def _first(cls, items) -> str | None:
        for item in items:
            found = cls.find_orphan(item)
            if found is not None:
                return found
        return None


class PiiRunSummaryPolicy:
    """FR-13 — ai_run 스텝·로그에 남길 런 요약. 모드와 타입별 고유 건수만 쓴다."""

    @staticmethod
    def render(scope: PiiRunScope) -> str:
        counts = scope.vault.counts()
        parts = [
            f"{pii_type.value}={counts[pii_type]}"
            for pii_type in DETECTION_PRIORITY
            if counts.get(pii_type)
        ]
        return f"mode={scope.mode.value} " + (" ".join(parts) or "none")
