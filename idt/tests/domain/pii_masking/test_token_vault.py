"""domain/pii_masking TokenVault/Registry 단위 테스트 (mock 금지)."""
from src.domain.pii_masking.schemas import PiiType, TokenVault, TokenVaultRegistry


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

    def test_size_reflects_mapping_count(self):
        vault = TokenVault()
        vault.get_or_create_placeholder(PiiType.RRN, "900101-1234567")
        vault.get_or_create_placeholder(PiiType.PHONE, "010-1111-2222")
        assert vault.size == 2


class TestTokenVaultRegistry:
    def test_same_session_returns_same_vault(self):
        registry = TokenVaultRegistry()
        assert registry.get("s1") is registry.get("s1")

    def test_different_sessions_isolated(self):
        registry = TokenVaultRegistry()
        assert registry.get("s1") is not registry.get("s2")

    def test_clear_removes_vault(self):
        registry = TokenVaultRegistry()
        v1 = registry.get("s1")
        v1.get_or_create_placeholder(PiiType.RRN, "900101-1234567")
        registry.clear("s1")
        # 새 vault가 생성되어 카운터가 초기화된다.
        assert registry.get("s1").size == 0
