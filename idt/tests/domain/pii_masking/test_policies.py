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


class TestBusinessNumber:
    def test_business_number_valid_checksum_returns_true(self):
        assert PiiMaskingPolicy.business_number_valid("123-45-67891") is True

    def test_business_number_wrong_checksum_returns_false(self):
        assert PiiMaskingPolicy.business_number_valid("123-45-67890") is False

    def test_business_number_other_format_returns_false(self):
        # 3-2-5 형식이 아니면 체크섬이 맞아도 사업자번호로 보지 않는다.
        assert PiiMaskingPolicy.business_number_valid("1234567891") is False


class TestAccount:
    def test_account_ten_to_fourteen_digits_is_valid(self):
        assert PiiMaskingPolicy.account_valid("110-123-456789") is True
        assert PiiMaskingPolicy.account_valid("123456-01-123456") is True

    def test_account_hyphen_date_is_rejected(self):
        assert PiiMaskingPolicy.account_valid("2026-11-02") is False

    def test_account_over_fourteen_digits_is_rejected(self):
        assert PiiMaskingPolicy.account_valid("20261102-0001-0007") is False

    def test_account_business_number_is_rejected(self):
        assert PiiMaskingPolicy.account_valid("123-45-67891") is False

    def test_is_valid_account_uses_account_rule(self):
        assert PiiMaskingPolicy.is_valid(PiiType.ACCOUNT, "2026-11-02") is False


class TestEmailValid:
    def test_two_char_tld_passes(self):
        assert PiiMaskingPolicy.email_valid("user@example.co") is True

    def test_one_char_tld_fails(self):
        assert PiiMaskingPolicy.email_valid("user@example.c") is False
