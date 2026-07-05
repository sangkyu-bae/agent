"""PII 탐지 정규식 상수 (도메인 규칙).

각 패턴은 RegexPiiDetector가 사용하며, 오탐 저감 검증은 PiiMaskingPolicy가 담당한다.
"""
import re

# 주민등록번호: YYMMDD-GxxxxxC (구분자 -, 공백 허용)
RRN_PATTERN = re.compile(r"\b\d{6}[-\s]?\d{7}\b")

# 휴대폰: 010/011/016/017/018/019 - 3~4 - 4
MOBILE_PATTERN = re.compile(r"\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b")
# 지역 유선: 02 또는 0XX - 3~4 - 4
LANDLINE_PATTERN = re.compile(r"\b0(?:2|\d{2})[-\s]?\d{3,4}[-\s]?\d{4}\b")

# 이메일 (약식 RFC)
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

# 카드번호: 13~19자리 (Visa16/Amex15/Diners14 등), 자리 사이 - 또는 공백 1개 허용.
# 패턴은 후보만 추리고 Luhn 체크섬(PiiMaskingPolicy.luhn_valid)으로 최종 확정한다.
CARD_PATTERN = re.compile(r"\b\d(?:[-\s]?\d){12,18}\b")

# 한국 계좌 휴리스틱: 2~6 - 2~6 - 2~6 그룹, 또는 10~14 연속 숫자.
# CARD/RRN/PHONE에 우선 점유되지 않은 잔여 숫자열만 후보가 된다(우선순위 처리).
ACCOUNT_PATTERN = re.compile(
    r"\b(?:\d{2,6}[-\s]\d{2,6}[-\s]\d{2,6}|\d{10,14})\b"
)
