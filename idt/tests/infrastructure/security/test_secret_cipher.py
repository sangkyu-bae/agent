"""Infrastructure 테스트: SecretCipher (Fernet 대칭암호화)."""
import pytest

from src.infrastructure.security.secret_cipher import SecretCipher


@pytest.fixture
def cipher() -> SecretCipher:
    return SecretCipher(SecretCipher.generate_key())


class TestSecretCipherRoundTrip:

    def test_encrypt_then_decrypt_returns_same_dict(self, cipher):
        data = {"api_key": "smithery_xxx", "profile": "p1"}
        token = cipher.encrypt_dict(data)
        assert isinstance(token, str)
        assert "smithery_xxx" not in token  # 평문 노출 없음
        assert cipher.decrypt_dict(token) == data

    def test_encrypt_none_returns_none(self, cipher):
        assert cipher.encrypt_dict(None) is None

    def test_decrypt_none_or_empty_returns_none(self, cipher):
        assert cipher.decrypt_dict(None) is None
        assert cipher.decrypt_dict("") is None

    def test_nested_dict_round_trip(self, cipher):
        data = {"headers": {"Authorization": "Bearer t"}, "profile": "p"}
        assert cipher.decrypt_dict(cipher.encrypt_dict(data)) == data


class TestSecretCipherKey:

    def test_empty_key_raises(self):
        with pytest.raises(ValueError):
            SecretCipher("")

    def test_two_ciphers_same_key_interoperate(self):
        key = SecretCipher.generate_key()
        token = SecretCipher(key).encrypt_dict({"a": "b"})
        assert SecretCipher(key).decrypt_dict(token) == {"a": "b"}
