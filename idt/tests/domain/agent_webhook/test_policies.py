"""WebhookSecretPolicy · WebhookSignaturePolicy 단위 테스트 (Design §6)."""
from src.domain.agent_webhook.policies import (
    WebhookSecretPolicy,
    WebhookSignaturePolicy,
)


class TestWebhookSecretPolicy:
    def test_generate_has_prefix_and_entropy(self):
        secret = WebhookSecretPolicy.generate()
        assert secret.startswith("whsec_")
        # token_urlsafe(32) ≈ 43자 + prefix 6자
        assert len(secret) >= 40

    def test_generate_is_unique(self):
        assert WebhookSecretPolicy.generate() != WebhookSecretPolicy.generate()

    def test_hint_is_last_4_chars(self):
        assert WebhookSecretPolicy.hint("whsec_abcdef1234") == "1234"


class TestWebhookSignaturePolicy:
    SECRET = "whsec_test_secret"
    BODY = b'{"query":"\xec\x95\x88\xeb\x85\x95"}'  # 유니코드 body — raw bytes 기준

    def test_sign_is_deterministic_with_prefix(self):
        s1 = WebhookSignaturePolicy.sign(self.SECRET, 1754500000, self.BODY)
        s2 = WebhookSignaturePolicy.sign(self.SECRET, 1754500000, self.BODY)
        assert s1 == s2
        assert s1.startswith("sha256=")

    def test_verify_accepts_valid_signature(self):
        ts = 1754500000
        sig = WebhookSignaturePolicy.sign(self.SECRET, ts, self.BODY)
        assert WebhookSignaturePolicy.verify(self.SECRET, ts, self.BODY, sig)

    def test_verify_rejects_forged_signature(self):
        ts = 1754500000
        sig = WebhookSignaturePolicy.sign("whsec_other_secret", ts, self.BODY)
        assert not WebhookSignaturePolicy.verify(self.SECRET, ts, self.BODY, sig)

    def test_verify_rejects_tampered_body(self):
        ts = 1754500000
        sig = WebhookSignaturePolicy.sign(self.SECRET, ts, self.BODY)
        assert not WebhookSignaturePolicy.verify(
            self.SECRET, ts, b'{"query":"changed"}', sig
        )

    def test_verify_rejects_timestamp_mismatch(self):
        sig = WebhookSignaturePolicy.sign(self.SECRET, 1754500000, self.BODY)
        assert not WebhookSignaturePolicy.verify(
            self.SECRET, 1754500001, self.BODY, sig
        )

    def test_timestamp_within_tolerance(self):
        now = 1754500000
        assert WebhookSignaturePolicy.is_timestamp_valid(now - 299, now)
        assert WebhookSignaturePolicy.is_timestamp_valid(now + 299, now)
        assert WebhookSignaturePolicy.is_timestamp_valid(now - 300, now)

    def test_timestamp_outside_tolerance(self):
        now = 1754500000
        assert not WebhookSignaturePolicy.is_timestamp_valid(now - 301, now)
        assert not WebhookSignaturePolicy.is_timestamp_valid(now + 301, now)
