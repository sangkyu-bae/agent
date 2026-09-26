"""MCP 호출자 신원 헤더 — 설정 값 객체와 클레임 정책 (순수 도메인).

Design Ref: mcp-identity-header §3.1 — 공용 MCP 서버 하나가 사용자별 자원을
다루려면 "누구의 자원인가"를 LLM 이 아니라 플랫폼이 호출마다 보증해야 한다.
클레임 값의 출처는 users 행뿐이며, 서명·시각·저장소는 이 모듈 밖에 둔다
(jose·SQLAlchemy import 금지, now 는 인자로 받는다).
"""
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from src.domain.auth.entities import User, UserStatus

_MASK = "****"
# RFC 7230 token — HTTP 헤더 이름으로 쓸 수 있는 문자만.
_HEADER_TOKEN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")

IdentityUnavailableReason = Literal[
    "no_subject", "user_not_found", "user_inactive", "claim_empty"
]


class ClaimSource(str, Enum):
    """클레임 값을 꺼낼 사용자 속성."""

    MAILBOX_UPN = "mailbox_upn"
    EMAIL = "email"


@dataclass(frozen=True)
class IdentityHeaderConfig:
    """서버별 신원 헤더 설정. 기본값은 mcp-outlook-server 계약(§3)과 같다."""

    secret: str = field(repr=False)
    audience: str
    issuer: str = "agent-builder"
    header_name: str = "X-MCP-Identity"
    claim_name: str = "preferred_username"
    claim_source: ClaimSource = ClaimSource.MAILBOX_UPN
    ttl_seconds: int = 300

    MIN_SECRET_LENGTH = 32
    MAX_TTL_SECONDS = 300
    RESERVED_CLAIMS = frozenset({"iss", "aud", "sub", "iat", "exp", "nbf", "jti"})

    @classmethod
    def from_dict(cls, raw: dict) -> "IdentityHeaderConfig":
        """저장·요청 dict → 검증된 설정. 규칙 위반은 ValueError."""
        if not isinstance(raw, dict):
            raise ValueError("identity_config must be an object")
        config = cls(
            secret=_require_text(raw.get("secret"), "secret"),
            audience=_require_text(raw.get("audience"), "audience"),
            issuer=_require_text(raw.get("issuer", cls.issuer), "issuer"),
            header_name=_require_text(raw.get("header_name", cls.header_name), "header_name"),
            claim_name=_require_text(raw.get("claim_name", cls.claim_name), "claim_name"),
            claim_source=_parse_source(raw.get("claim_source", ClaimSource.MAILBOX_UPN)),
            ttl_seconds=_parse_ttl(raw.get("ttl_seconds", cls.ttl_seconds)),
        )
        config._validate()
        return config

    @classmethod
    def merge_update(
        cls, existing: "IdentityHeaderConfig | None", raw: dict
    ) -> "IdentityHeaderConfig":
        """PUT 규칙 (Design §4.2) — 요청 객체는 '전체 설정'이되 secret 만 예외다.

        secret 이 비어 있으면 기존 비밀을 유지한다. 관리자 화면은 비밀을 다시
        보여주지 않으므로(마스킹) 다른 필드만 고칠 때 비밀을 재입력하게 하면
        안 된다. 기존 설정이 없는데 비밀도 없으면 만들 수 없다.
        """
        if not isinstance(raw, dict):
            raise ValueError("identity_config must be an object")
        secret = raw.get("secret")
        if isinstance(secret, str) and secret.strip():
            return cls.from_dict(raw)
        if existing is None:
            raise ValueError("identity secret is required for a new identity_config")
        return cls.from_dict({**raw, "secret": existing.secret})

    def _validate(self) -> None:
        if len(self.secret) < self.MIN_SECRET_LENGTH:
            raise ValueError(
                f"identity secret must be at least {self.MIN_SECRET_LENGTH} characters"
            )
        if not _HEADER_TOKEN.match(self.header_name):
            raise ValueError("identity header_name is not a valid HTTP header name")
        if self.claim_name in self.RESERVED_CLAIMS:
            raise ValueError(f"identity claim_name {self.claim_name!r} is reserved")

    def to_dict(self) -> dict:
        """저장용 평문 dict. 저장 경계에서 반드시 암호화한다."""
        return {**self._public_fields(), "secret": self.secret}

    def masked(self) -> dict:
        """응답·로그용. secret 만 가린다."""
        return {**self._public_fields(), "secret": _MASK}

    def _public_fields(self) -> dict:
        return {
            "audience": self.audience,
            "issuer": self.issuer,
            "header_name": self.header_name,
            "claim_name": self.claim_name,
            "claim_source": self.claim_source.value,
            "ttl_seconds": self.ttl_seconds,
        }


class IdentityUnavailableError(Exception):
    """신원 헤더를 만들 수 없다 — MCP 서버에 연결하기 전에 멈춘다 (FR-07)."""

    def __init__(
        self,
        reason: IdentityUnavailableReason,
        source: ClaimSource | None = None,
        subject: str | None = None,
    ) -> None:
        super().__init__(f"identity unavailable: {reason}")
        self.reason = reason
        self.source = source
        # 로그 추적용 실행 주체 (Check G-4). 사용자 문구에는 쓰지 않는다.
        self.subject = subject


_USER_MESSAGES: dict[str, str] = {
    "no_subject": "이 도구는 사용자 신원이 필요한데 실행 사용자를 알 수 없습니다.",
    "user_not_found": "실행 사용자 정보를 찾을 수 없습니다.",
    "user_inactive": "승인되지 않은 사용자는 이 도구를 사용할 수 없습니다.",
}
_CLAIM_LABELS: dict[ClaimSource, str] = {
    ClaimSource.MAILBOX_UPN: "메일함",
    ClaimSource.EMAIL: "로그인 이메일",
}


class IdentityClaimPolicy:
    """실행 주체 → 클레임 판정·조립 규칙."""

    @staticmethod
    def require_subject(subject_user_id: str | None) -> str:
        subject = (subject_user_id or "").strip()
        if not subject:
            raise IdentityUnavailableError("no_subject")
        return subject

    @staticmethod
    def resolve_claim_value(user: User | None, source: ClaimSource) -> str:
        """클레임에 넣을 값. users 행 외의 출처는 없다."""
        if user is None:
            raise IdentityUnavailableError("user_not_found", source)
        if user.status != UserStatus.APPROVED:
            raise IdentityUnavailableError("user_inactive", source)
        raw = user.mailbox_upn if source is ClaimSource.MAILBOX_UPN else user.email
        value = (raw or "").strip()
        if not value:
            raise IdentityUnavailableError("claim_empty", source)
        return value

    @staticmethod
    def build_claims(
        config: IdentityHeaderConfig,
        subject_user_id: str,
        claim_value: str,
        now: int,
    ) -> dict:
        return {
            "iss": config.issuer,
            "aud": config.audience,
            "sub": subject_user_id,
            "iat": now,
            "exp": now + config.ttl_seconds,
            config.claim_name: claim_value,
        }

    @staticmethod
    def user_message(error: IdentityUnavailableError) -> str:
        """사용자에게 보여 줄 안내문 (Design §6.1)."""
        if error.reason != "claim_empty":
            return _USER_MESSAGES[error.reason]
        label = _CLAIM_LABELS.get(error.source or ClaimSource.MAILBOX_UPN, "메일함")
        return f"{label}이 등록되지 않았습니다. 관리자에게 등록을 요청하세요."


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"identity {name} is required")
    return value.strip()


def _parse_source(value: object) -> ClaimSource:
    try:
        return ClaimSource(value)
    except ValueError as e:
        raise ValueError(f"identity claim_source {value!r} is not supported") from e


def _parse_ttl(value: object) -> int:
    # bool 은 int 의 하위 타입이라 명시적으로 막는다.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("identity ttl_seconds must be an integer")
    if not 1 <= value <= IdentityHeaderConfig.MAX_TTL_SECONDS:
        raise ValueError("identity ttl_seconds must be between 1 and 300")
    return value
