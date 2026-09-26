"""HmacIdentityTokenSigner — HS256 서명 + mcp-outlook-server 검증기 교차 검증.

Design Ref: mcp-identity-header §8.2 (#4, #5). 교차 검증은 서버
`mcp_shared.auth.HmacTokenVerifier.verify` 의 PyJWT 호출과 수명 상한을
그대로 재현한다 (형제 저장소를 import 하지 않기 위해 규칙을 복제).
"""
import time

import jwt as pyjwt
import pytest
from jose import jwt as jose_jwt

from src.domain.mcp_registry.identity import IdentityClaimPolicy, IdentityHeaderConfig
from src.infrastructure.mcp_registry.identity_token import HmacIdentityTokenSigner

_SECRET = "k" * 40


def _server_verify(token: str, *, secret: str, audience: str, issuer: str) -> dict:
    """agent_mcp/common/src/mcp_shared/auth/verifier.py HmacTokenVerifier.verify 재현."""
    claims = pyjwt.decode(
        token, secret, algorithms=["HS256"], audience=audience, issuer=issuer,
        leeway=30, options={"require": ["exp", "iat", "aud", "iss", "sub"]},
    )
    assert claims["exp"] - claims["iat"] <= 300
    return claims


def _config(**overrides) -> IdentityHeaderConfig:
    raw = {"audience": "mcp-outlook-server", "secret": _SECRET}
    raw.update(overrides)
    return IdentityHeaderConfig.from_dict(raw)


class TestSign:
    def test_HS256_헤더로_서명한다(self):
        token = HmacIdentityTokenSigner().sign({"sub": "7"}, _SECRET)
        assert jose_jwt.get_unverified_header(token)["alg"] == "HS256"

    def test_같은_비밀로_복호화하면_클레임이_같다(self):
        claims = {"iss": "i", "aud": "a", "sub": "7", "iat": 1, "exp": 2, "x": "y"}
        token = HmacIdentityTokenSigner().sign(claims, _SECRET)
        decoded = jose_jwt.decode(
            token, _SECRET, algorithms=["HS256"], audience="a",
            options={"verify_exp": False},
        )
        assert decoded == claims

    def test_다른_비밀로는_검증되지_않는다(self):
        token = HmacIdentityTokenSigner().sign({"sub": "7"}, _SECRET)
        with pytest.raises(pyjwt.InvalidSignatureError):
            pyjwt.decode(token, "z" * 40, algorithms=["HS256"])


class TestServerCrossVerification:
    def test_서버_검증기를_통과하고_메일함_클레임이_실린다(self):
        cfg = _config()
        claims = IdentityClaimPolicy.build_claims(
            cfg, "7", "kim@corp.com", now=int(time.time())
        )
        token = HmacIdentityTokenSigner().sign(claims, cfg.secret)
        verified = _server_verify(
            token, secret=_SECRET, audience="mcp-outlook-server", issuer="agent-builder"
        )
        assert verified["preferred_username"] == "kim@corp.com"
        assert verified["sub"] == "7"

    def test_audience가_다르면_서버가_거부한다(self):
        """서버별 audience — 다른 MCP 서버용 토큰이 통과하지 않는다."""
        cfg = _config(audience="mcp-calendar-server")
        claims = IdentityClaimPolicy.build_claims(cfg, "7", "kim@corp.com", now=int(time.time()))
        token = HmacIdentityTokenSigner().sign(claims, cfg.secret)
        with pytest.raises(pyjwt.InvalidAudienceError):
            _server_verify(
                token, secret=_SECRET, audience="mcp-outlook-server", issuer="agent-builder"
            )
