"""신원 헤더 도메인 모델 — IdentityHeaderConfig / IdentityClaimPolicy.

Design Ref: mcp-identity-header §3.1, §6.1, §8.2 (#1~#3). mock 금지 (순수 도메인).
"""
import pytest

from src.domain.auth.entities import User, UserStatus
from src.domain.mcp_registry.identity import (
    ClaimSource,
    IdentityClaimPolicy,
    IdentityHeaderConfig,
    IdentityUnavailableError,
)

_SECRET = "s" * 32


def _raw(**overrides) -> dict:
    raw = {"audience": "mcp-outlook-server", "secret": _SECRET}
    raw.update(overrides)
    return raw


def _user(
    mailbox: str | None = "kim@corp.com",
    status: UserStatus = UserStatus.APPROVED,
    email: str = "kim@login.local",
) -> User:
    return User(
        id=7, email=email, password_hash="h", status=status, mailbox_upn=mailbox
    )


class TestIdentityHeaderConfigFromDict:
    def test_필수값만_주면_계약_기본값으로_채운다(self):
        cfg = IdentityHeaderConfig.from_dict(_raw())
        assert cfg.issuer == "agent-builder"
        assert cfg.header_name == "X-MCP-Identity"
        assert cfg.claim_name == "preferred_username"
        assert cfg.claim_source is ClaimSource.MAILBOX_UPN
        assert cfg.ttl_seconds == 300

    def test_전체_필드를_받는다(self):
        cfg = IdentityHeaderConfig.from_dict(
            _raw(
                issuer="iss-x", header_name="X-Id", claim_name="email",
                claim_source="email", ttl_seconds=60,
            )
        )
        assert (cfg.issuer, cfg.header_name, cfg.claim_name) == ("iss-x", "X-Id", "email")
        assert cfg.claim_source is ClaimSource.EMAIL
        assert cfg.ttl_seconds == 60

    @pytest.mark.parametrize(
        "overrides",
        [
            {"secret": "s" * 31},
            {"secret": None},
            {"audience": ""},
            {"audience": "   "},
            {"ttl_seconds": 0},
            {"ttl_seconds": 301},
            {"claim_source": "phone"},
            {"header_name": "X MCP"},
            {"header_name": ""},
            {"claim_name": ""},
        ],
    )
    def test_잘못된_값은_ValueError(self, overrides):
        with pytest.raises(ValueError):
            IdentityHeaderConfig.from_dict(_raw(**overrides))

    @pytest.mark.parametrize("reserved", ["sub", "iss", "aud", "exp", "iat", "nbf", "jti"])
    def test_예약_클레임명은_거부한다(self, reserved):
        with pytest.raises(ValueError):
            IdentityHeaderConfig.from_dict(_raw(claim_name=reserved))

    def test_ttl_불리언은_정수로_보지_않는다(self):
        with pytest.raises(ValueError):
            IdentityHeaderConfig.from_dict(_raw(ttl_seconds=True))

    def test_dict가_아니면_ValueError(self):
        with pytest.raises(ValueError):
            IdentityHeaderConfig.from_dict("not-a-dict")  # type: ignore[arg-type]


class TestIdentityHeaderConfigSerialization:
    def test_to_dict_from_dict_왕복(self):
        cfg = IdentityHeaderConfig.from_dict(_raw(claim_source="email", ttl_seconds=120))
        assert IdentityHeaderConfig.from_dict(cfg.to_dict()) == cfg

    def test_to_dict_의_claim_source는_문자열(self):
        assert IdentityHeaderConfig.from_dict(_raw()).to_dict()["claim_source"] == "mailbox_upn"

    def test_masked는_secret만_가린다(self):
        masked = IdentityHeaderConfig.from_dict(_raw()).masked()
        assert masked["secret"] == "****"
        assert masked["audience"] == "mcp-outlook-server"
        assert _SECRET not in str(masked)

    def test_repr에_secret이_나오지_않는다(self):
        """로그·예외 메시지로 새는 경로 차단 (FR-10)."""
        assert _SECRET not in repr(IdentityHeaderConfig.from_dict(_raw()))


class TestResolveClaimValue:
    def test_메일함_소스는_mailbox_upn(self):
        assert (
            IdentityClaimPolicy.resolve_claim_value(_user(), ClaimSource.MAILBOX_UPN)
            == "kim@corp.com"
        )

    def test_이메일_소스는_로그인_email(self):
        assert (
            IdentityClaimPolicy.resolve_claim_value(_user(), ClaimSource.EMAIL)
            == "kim@login.local"
        )

    def test_사용자_없음(self):
        with pytest.raises(IdentityUnavailableError) as e:
            IdentityClaimPolicy.resolve_claim_value(None, ClaimSource.MAILBOX_UPN)
        assert e.value.reason == "user_not_found"

    @pytest.mark.parametrize("status", [UserStatus.PENDING, UserStatus.REJECTED])
    def test_승인되지_않은_사용자(self, status):
        with pytest.raises(IdentityUnavailableError) as e:
            IdentityClaimPolicy.resolve_claim_value(
                _user(status=status), ClaimSource.MAILBOX_UPN
            )
        assert e.value.reason == "user_inactive"

    @pytest.mark.parametrize("mailbox", [None, "", "   "])
    def test_메일함_미등록(self, mailbox):
        with pytest.raises(IdentityUnavailableError) as e:
            IdentityClaimPolicy.resolve_claim_value(
                _user(mailbox=mailbox), ClaimSource.MAILBOX_UPN
            )
        assert e.value.reason == "claim_empty"
        assert e.value.source is ClaimSource.MAILBOX_UPN


class TestRequireSubject:
    @pytest.mark.parametrize("subject", [None, "", "  "])
    def test_주체가_없으면_no_subject(self, subject):
        with pytest.raises(IdentityUnavailableError) as e:
            IdentityClaimPolicy.require_subject(subject)
        assert e.value.reason == "no_subject"

    def test_주체가_있으면_앞뒤_공백을_제거해_돌려준다(self):
        assert IdentityClaimPolicy.require_subject(" 7 ") == "7"


class TestBuildClaims:
    def test_계약_클레임을_조립한다(self):
        cfg = IdentityHeaderConfig.from_dict(_raw())
        claims = IdentityClaimPolicy.build_claims(cfg, "7", "kim@corp.com", now=1000)
        assert claims == {
            "iss": "agent-builder",
            "aud": "mcp-outlook-server",
            "sub": "7",
            "iat": 1000,
            "exp": 1300,
            "preferred_username": "kim@corp.com",
        }

    def test_ttl을_반영한다(self):
        cfg = IdentityHeaderConfig.from_dict(_raw(ttl_seconds=60, claim_name="email"))
        claims = IdentityClaimPolicy.build_claims(cfg, "7", "a@b.c", now=1000)
        assert claims["exp"] == 1060
        assert claims["email"] == "a@b.c"


class TestUserMessage:
    @pytest.mark.parametrize(
        "reason", ["no_subject", "user_not_found", "user_inactive", "claim_empty"]
    )
    def test_모든_사유에_안내문이_있다(self, reason):
        err = IdentityUnavailableError(reason, source=ClaimSource.MAILBOX_UPN)
        assert IdentityClaimPolicy.user_message(err)

    def test_메일함_미등록은_관리자_요청을_안내한다(self):
        err = IdentityUnavailableError("claim_empty", source=ClaimSource.MAILBOX_UPN)
        message = IdentityClaimPolicy.user_message(err)
        assert "메일함" in message and "관리자" in message

    def test_이메일_소스_미등록은_로그인_이메일로_안내한다(self):
        err = IdentityUnavailableError("claim_empty", source=ClaimSource.EMAIL)
        assert "로그인 이메일" in IdentityClaimPolicy.user_message(err)
