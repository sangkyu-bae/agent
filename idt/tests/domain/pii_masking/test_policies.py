"""domain/pii_masking/policies 단위 테스트 (mock 금지)."""
from src.domain.pii_masking.policies import PiiMaskingPolicy
from src.domain.pii_masking.schemas import PiiType


class TestLuhn:
    def test_valid_visa_test_number_passes(self):
        # 잘 알려진 Luhn 유효 테스트 카드번호.
        assert PiiMaskingPolicy.luhn_valid("4539 1488 0343 6467") is True

    def test_invalid_number_fails(self):
        assert PiiMaskingPolicy.luhn_valid("1234 5678 9012 3456") is False

    def test_too_short_fails(self):
        assert PiiMaskingPolicy.luhn_valid("4539") is False


class TestRrn:
    def test_valid_rrn_passes(self):
        assert PiiMaskingPolicy.rrn_valid("900101-1234567") is True

    def test_invalid_month_fails(self):
        assert PiiMaskingPolicy.rrn_valid("901301-1234567") is False

    def test_invalid_day_fails(self):
        assert PiiMaskingPolicy.rrn_valid("900132-1234567") is False

    def test_invalid_gender_code_fails(self):
        assert PiiMaskingPolicy.rrn_valid("900101-9234567") is False

    def test_wrong_length_fails(self):
        assert PiiMaskingPolicy.rrn_valid("90010-1234567") is False


class TestIsValid:
    def test_card_uses_luhn(self):
        assert PiiMaskingPolicy.is_valid(PiiType.CARD, "4539148803436467") is True
        assert PiiMaskingPolicy.is_valid(PiiType.CARD, "1111111111111111") is False

    def test_phone_always_valid(self):
        assert PiiMaskingPolicy.is_valid(PiiType.PHONE, "010-1234-5678") is True

    def test_email_valid_tld(self):
        assert PiiMaskingPolicy.is_valid(PiiType.EMAIL, "a@b.com") is True

    def test_email_too_short_tld_rejected(self):
        # TLD 1글자 → 오탐 저감으로 EMAIL 아님.
        assert PiiMaskingPolicy.is_valid(PiiType.EMAIL, "a@b.c") is False

    def test_email_numeric_tld_rejected(self):
        assert PiiMaskingPolicy.is_valid(PiiType.EMAIL, "a@b.12") is False


class TestEmailValid:
    def test_two_char_tld_passes(self):
        assert PiiMaskingPolicy.email_valid("user@example.co") is True

    def test_one_char_tld_fails(self):
        assert PiiMaskingPolicy.email_valid("user@example.c") is False
