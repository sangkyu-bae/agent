"""PII 탐지 정규식 상수 (도메인 규칙). 패턴 본문의 SoT.

각 패턴은 RegexPiiDetector가 사용하며, 오탐 저감 검증은 PiiMaskingPolicy가 담당한다.
규칙을 바꿀 때는 tests/fixtures/pii_masking/ 코퍼스에 문장을 먼저 추가한다.

Design Ref: pii-masking-integration §10.1 — 2026-11 재작성 이력:
- `\\b` 제거: 파이썬에서 한글도 `\\w`라 `010-1234-5678로`의 숫자와 조사 사이가
  경계가 아니다. 조사가 붙으면 전 타입이 미탐지됐다. 숫자·대시 lookaround로 교체.
- EMAIL: `\\w`가 한글을 포함해 `hong@example.co.kr입니다`의 조사까지 값이 됐다.
  ASCII로 한정.
- ACCOUNT: 공백 구분을 제거(표의 숫자열 오탐). 대시 그룹은 2~7자리, 3~4그룹으로
  넓혀 `3333-01-1234567`, `302-1234-5678-91`을 탐지한다.
  금액 단위가 붙은 연속 숫자는 제외.
- CARD: 임의 위치 공백 허용을 제거(표의 숫자열을 이어 붙임). 실제 표기 형식만 허용.
- PHONE: 구분자에 점·괄호·공백 낀 대시 추가, 국제 표기 추가.
  유선은 실제 지역번호로 한정.
- 대시: 전각 대시(–, —)를 하이픈과 같이 취급한다. PDF 추출본에 흔하다.
- 공백 구분자는 스페이스만 허용: 개행을 넘어 표의 다음 행과 이어지지 않게 한다.
"""
import re

_DASH = r"[-–—]"
# 숫자열 경계. `\b`를 쓰지 않는다(위 docstring). 대시는 더 긴 번호의 일부를 막는다.
_NUM_START = r"(?<![\d\-–—])"
_NUM_END = r"(?![\d\-–—])"
_PHONE_SEP = r"(?: ?" + _DASH + r" ?|[. ]|\) ?)?"

# 금액·비율 단위. 이 단위가 붙은 연속 숫자는 계좌가 아니다.
_AMOUNT_UNIT = r"(?: ?(?:원|만|억|천|조|달러|%|KRW|USD))"

# 주민등록번호: YYMMDD-GxxxxxC (구분자 대시, 스페이스 허용)
RRN_PATTERN = re.compile(
    _NUM_START + r"\d{6}(?: ?" + _DASH + r" ?| )?\d{7}" + _NUM_END
)

# 휴대폰: 01X 또는 +82-1X, 가운데 3~4자리, 끝 4자리
MOBILE_PATTERN = re.compile(
    r"(?<![\d+\-–—])(?:\+82[-. ]?1[016789]|01[016789])"
    + _PHONE_SEP + r"\d{3,4}" + _PHONE_SEP + r"\d{4}" + _NUM_END
)
# 유선: 실제 지역번호(02, 03X, 04X, 05X, 06X)와 인터넷전화 070
LANDLINE_PATTERN = re.compile(
    _NUM_START + r"0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4]|70)"
    + _PHONE_SEP + r"\d{3,4}" + _PHONE_SEP + r"\d{4}" + _NUM_END
)

# 이메일 (약식 RFC, ASCII)
EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+"
    r"(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)

# 카드번호: 4-4-4-4(16자리), 4-6-5(Amex)·4-6-4(Diners), 또는 13~19자리 연속.
# 구분자는 그룹 사이에서 같아야 한다. 앞뒤에 숫자 그룹이 이어지면 표의 숫자열로 본다.
# 패턴은 후보만 추리고 Luhn 체크섬(PiiMaskingPolicy.luhn_valid)으로 최종 확정한다.
CARD_PATTERN = re.compile(
    _NUM_START + r"(?<!\d )"
    r"(?:\d{4}([-–— ])\d{4}\1\d{4}\1\d{4}"
    r"|\d{4}([-–— ])\d{6}\2\d{4,5}"
    r"|\d{13,19})"
    + _NUM_END + r"(?! \d)"
)

# 한국 계좌 휴리스틱: 대시 3~4그룹, 또는 10~14자리 연속 숫자.
# 총 자릿수·날짜·사업자번호 제외는 PiiMaskingPolicy.account_valid가 맡는다.
# CARD/RRN/PHONE에 우선 점유되지 않은 잔여 숫자열만 후보가 된다(우선순위 처리).
ACCOUNT_PATTERN = re.compile(
    r"(?<![\d.,\-–—])"
    r"(?:\d{2,7}(?:" + _DASH + r"\d{2,7}){2,3}"
    r"|\d{10,14}(?!\d)(?!" + _AMOUNT_UNIT + r"))"
    r"(?![\d\-–—]|\.\d)"
)

# 사업자등록번호 표기. 체크섬은 PiiMaskingPolicy.business_number_valid가 검사한다.
BUSINESS_NUMBER_FORMAT = re.compile(r"\d{3}-\d{2}-\d{5}")
