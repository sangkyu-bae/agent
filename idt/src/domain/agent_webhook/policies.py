"""agent-webhook 도메인 정책 — 시크릿 생성·HMAC 서명 검증 규칙.

Design D1/D2:
- 서명 대상: "{timestamp}.{raw_body}" (raw bytes 기준 — 재직렬화 금지)
- X-Webhook-Signature: "sha256=<hex>" — HMAC-SHA256, 상수 시간 비교
- 타임스탬프 허용창 ±300초 (재생 공격 방어)

stdlib(hmac/hashlib/secrets)만 사용 — domain 레이어 금지 사항 저촉 없음.
Outbound(M2) 발송 서명도 sign()을 그대로 재사용한다.
"""
import hmac
import hashlib
import secrets
from urllib.parse import urlparse


class WebhookSecretPolicy:
    PREFIX = "whsec_"
    HINT_LEN = 4
    _TOKEN_BYTES = 32

    @staticmethod
    def generate() -> str:
        return WebhookSecretPolicy.PREFIX + secrets.token_urlsafe(
            WebhookSecretPolicy._TOKEN_BYTES
        )

    @staticmethod
    def hint(secret: str) -> str:
        return secret[-WebhookSecretPolicy.HINT_LEN:]


class WebhookSignaturePolicy:
    HEADER_TIMESTAMP = "X-Webhook-Timestamp"
    HEADER_SIGNATURE = "X-Webhook-Signature"
    TOLERANCE_SECONDS = 300
    SIGNATURE_PREFIX = "sha256="

    @staticmethod
    def sign(secret: str, timestamp: int, raw_body: bytes) -> str:
        digest = hmac.new(
            secret.encode("utf-8"),
            f"{timestamp}.".encode("utf-8") + raw_body,
            hashlib.sha256,
        ).hexdigest()
        return WebhookSignaturePolicy.SIGNATURE_PREFIX + digest

    @staticmethod
    def is_timestamp_valid(timestamp: int, now: int) -> bool:
        return abs(now - timestamp) <= WebhookSignaturePolicy.TOLERANCE_SECONDS

    @staticmethod
    def verify(
        secret: str, timestamp: int, raw_body: bytes, signature: str
    ) -> bool:
        expected = WebhookSignaturePolicy.sign(secret, timestamp, raw_body)
        return hmac.compare_digest(expected, signature)


class WebhookOutboundPolicy:
    """outbound 발송 규칙 (M2 Design D13/D18).

    - 재시도: 총 시도 최대 4회(최초 1 + 재시도 3) · 백오프 1/2/4초.
    - 5xx·연결 오류만 재시도 — 4xx는 수신측 명시 거부이므로 즉시 중단.
    - URL은 http/https 스킴만 허용 (내부 IP 차단 없음 — 사내망 수신이 정상 유스케이스).
    """

    ALLOWED_SCHEMES = ("http", "https")
    MAX_RETRIES = 3
    BACKOFF_SECONDS = (1.0, 2.0, 4.0)
    REQUEST_TIMEOUT_SECONDS = 10.0
    ERROR_MESSAGE_MAX = 2000
    EVENT_RUN_COMPLETED = "agent.run.completed"

    @staticmethod
    def is_valid_url(url: str) -> bool:
        parsed = urlparse(url)
        return (
            parsed.scheme in WebhookOutboundPolicy.ALLOWED_SCHEMES
            and bool(parsed.netloc)
        )

    @staticmethod
    def should_retry(status_code: int | None) -> bool:
        if status_code is None:
            return True  # 연결 실패·타임아웃
        return status_code >= 500
