"""infrastructure/pii_masking/regex_detectors 단위 테스트 (mock 금지)."""
from src.domain.pii_masking.schemas import PiiType
from src.infrastructure.pii_masking.regex_detectors import RegexPiiDetector


def _types(text: str) -> list[PiiType]:
    return [m.pii_type for m in RegexPiiDetector().detect(text)]


class TestSingleType:
    def test_detects_rrn(self):
        matches = RegexPiiDetector().detect("주민번호 900101-1234567 입니다")
        assert len(matches) == 1
        assert matches[0].pii_type is PiiType.RRN
        assert matches[0].text == "900101-1234567"

    def test_detects_mobile_phone(self):
        assert PiiType.PHONE in _types("전화 010-1234-5678")

    def test_detects_landline_phone(self):
        assert PiiType.PHONE in _types("회사 02-123-4567")

    def test_detects_email(self):
        assert PiiType.EMAIL in _types("메일 user@example.com 로")

    def test_detects_valid_card_via_luhn(self):
        assert PiiType.CARD in _types("카드 4539 1488 0343 6467")

    def test_detects_amex_15_digit_card(self):
        # Amex 테스트 번호(15자리, Luhn 유효).
        assert PiiType.CARD in _types("카드 378282246310005")

    def test_detects_diners_14_digit_card(self):
        # Diners 테스트 번호(14자리, Luhn 유효).
        assert PiiType.CARD in _types("카드 30569309025904")

    def test_detects_account_heuristic(self):
        assert PiiType.ACCOUNT in _types("계좌 123-456-789012")


class TestFalsePositiveReduction:
    def test_invalid_rrn_not_detected_as_rrn(self):
        # 잘못된 월(13월) → RRN 아님. (다른 타입으로 잡힐 수는 있음)
        assert PiiType.RRN not in _types("번호 901301-1234567")

    def test_non_luhn_16_digits_not_card(self):
        types = _types("숫자 1234 5678 9012 3456")
        assert PiiType.CARD not in types

    def test_plain_year_not_masked(self):
        assert _types("2024년 매출 보고서") == []


class TestPriorityAndOverlap:
    def test_card_wins_over_account_for_same_span(self):
        # Luhn 유효 16자리 → CARD가 점유, ACCOUNT 중복 금지.
        types = _types("4539148803436467")
        assert types == [PiiType.CARD]

    def test_mobile_not_double_counted_as_account(self):
        # 010-1234-5678 은 PHONE 우선, ACCOUNT로 중복 탐지되지 않음.
        types = _types("010-1234-5678")
        assert types == [PiiType.PHONE]

    def test_multiple_distinct_pii_all_detected(self):
        text = "홍길동 900101-1234567, 010-1234-5678, hong@test.com"
        types = set(_types(text))
        assert {PiiType.RRN, PiiType.PHONE, PiiType.EMAIL} <= types

    def test_matches_sorted_by_start(self):
        text = "010-1234-5678 그리고 900101-1234567"
        matches = RegexPiiDetector().detect(text)
        starts = [m.start for m in matches]
        assert starts == sorted(starts)
