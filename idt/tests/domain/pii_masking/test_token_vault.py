"""domain/pii_masking TokenVault/PiiRunScope 단위 테스트 (mock 금지)."""
import pytest
from src.domain.pii_masking.schemas import (
    PiiMaskingMode,
    PiiRunScope,
    PiiType,
    TokenVault,
)


class TestTokenVault:
    def test_same_original_returns_same_placeholder(self):
        vault = TokenVault()
        first = vault.get_or_create_placeholder(PiiType.RRN, "900101-1234567")
        second = vault.get_or_create_placeholder(PiiType.RRN, "900101-1234567")
        assert first == second == "[RRN_1]"

    def test_different_originals_increment_counter(self):
        vault = TokenVault()
        p1 = vault.get_or_create_placeholder(PiiType.PHONE, "010-1111-2222")
        p2 = vault.get_or_create_placeholder(PiiType.PHONE, "010-3333-4444")
        assert p1 == "[PHONE_1]"
        assert p2 == "[PHONE_2]"

    def test_counter_is_per_type(self):
        vault = TokenVault()
        rrn = vault.get_or_create_placeholder(PiiType.RRN, "900101-1234567")
        card = vault.get_or_create_placeholder(PiiType.CARD, "4539148803436467")
        assert rrn == "[RRN_1]"
        assert card == "[CARD_1]"

    def test_restore_replaces_placeholder_with_original(self):
        vault = TokenVault()
        ph = vault.get_or_create_placeholder(PiiType.EMAIL, "user@example.com")
        restored = vault.restore(f"연락은 {ph} 으로 주세요")
        assert restored == "연락은 user@example.com 으로 주세요"

    def test_restore_lowercase_placeholder_restores_original(self):
        # Design §3.3: LLM이 대소문자를 바꾼 변형만 원복한다.
        vault = TokenVault()
        vault.get_or_create_placeholder(PiiType.PHONE, "010-1111-2222")
        assert vault.restore("번호 [phone_1]") == "번호 010-1111-2222"

    def test_restore_two_digit_number_not_confused_with_one_digit(self):
        vault = TokenVault()
        for i in range(11):
            vault.get_or_create_placeholder(PiiType.PHONE, f"010-0000-{i:04d}")
        assert vault.restore("[PHONE_1] [PHONE_11]") == "010-0000-0000 010-0000-0010"

    def test_size_reflects_mapping_count(self):
        vault = TokenVault()
        vault.get_or_create_placeholder(PiiType.RRN, "900101-1234567")
        vault.get_or_create_placeholder(PiiType.PHONE, "010-1111-2222")
        assert vault.size == 2

    def test_counts_returns_unique_values_per_type(self):
        vault = TokenVault()
        vault.get_or_create_placeholder(PiiType.PHONE, "010-1111-2222")
        vault.get_or_create_placeholder(PiiType.PHONE, "010-1111-2222")
        vault.get_or_create_placeholder(PiiType.PHONE, "010-3333-4444")
        vault.get_or_create_placeholder(PiiType.RRN, "900101-1234567")
        assert vault.counts() == {PiiType.PHONE: 2, PiiType.RRN: 1}


class TestReserveLiterals:
    def test_reserve_literals_new_placeholder_skips_literal_number(self):
        # Design §6.2: 입력에 이미 있던 `[PHONE_1]` 문자열과 번호가 겹치면 안 된다.
        vault = TokenVault()
        vault.reserve_literals("양식의 [PHONE_1] 칸을 채워 주세요")
        assert vault.get_or_create_placeholder(
            PiiType.PHONE, "010-1111-2222"
        ) == "[PHONE_2]"

    def test_reserve_literals_restore_keeps_literal_text(self):
        vault = TokenVault()
        vault.reserve_literals("[PHONE_1] 칸")
        vault.get_or_create_placeholder(PiiType.PHONE, "010-1111-2222")
        assert vault.restore("[PHONE_1] 칸, [PHONE_2]") == (
            "[PHONE_1] 칸, 010-1111-2222"
        )

    def test_is_orphan_unknown_placeholder_returns_true(self):
        assert TokenVault().is_orphan("[PHONE_9]") is True

    def test_is_orphan_reserved_literal_returns_false(self):
        vault = TokenVault()
        vault.reserve_literals("[PHONE_9]")
        assert vault.is_orphan("[PHONE_9]") is False

    def test_reserve_literals_counts_excludes_literal(self):
        vault = TokenVault()
        vault.reserve_literals("[PHONE_1]")
        assert vault.counts() == {}


class TestPiiRunScope:
    def test_scope_default_vault_is_not_shared_between_scopes(self):
        first = PiiRunScope(mode=PiiMaskingMode.ON)
        second = PiiRunScope(mode=PiiMaskingMode.ON)
        assert first.vault is not second.vault

    @pytest.mark.parametrize("value", ["shadow", "on"])
    def test_mode_accepts_declared_values(self, value):
        assert PiiMaskingMode(value).value == value

    def test_mode_rejects_typo(self):
        with pytest.raises(ValueError):
            PiiMaskingMode("onn")
