"""SecretCipher: dict 시크릿을 Fernet 대칭암호화한다.

infrastructure 레이어 — 비즈니스 규칙 없음.
MCP 서버 등록의 auth_config/server_config를 DB 저장 전 암호화하고
조회 후 복호화하는 데 사용한다. 평문은 앱 메모리 한정으로만 다룬다.
"""
import json

from cryptography.fernet import Fernet


class SecretCipher:
    """Fernet 기반 dict 암복호화기.

    key는 urlsafe base64 32바이트 Fernet 키여야 한다.
    (설정: settings.mcp_secret_key — 하드코딩 금지)
    """

    def __init__(self, key: str) -> None:
        if not key:
            raise ValueError("SecretCipher requires a non-empty Fernet key")
        self._fernet = Fernet(key)

    def encrypt_dict(self, data: dict | None) -> str | None:
        """dict → JSON → Fernet 토큰(str). None이면 None 반환."""
        if data is None:
            return None
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
        return self._fernet.encrypt(payload.encode("utf-8")).decode("utf-8")

    def decrypt_dict(self, token: str | None) -> dict | None:
        """Fernet 토큰(str) → dict. None/빈 값이면 None 반환."""
        if not token:
            return None
        decrypted = self._fernet.decrypt(token.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))

    @staticmethod
    def generate_key() -> str:
        """새 Fernet 키를 생성한다 (운영 키 발급/로테이션 보조)."""
        return Fernet.generate_key().decode("utf-8")
