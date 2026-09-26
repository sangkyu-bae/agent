"""MCP 호출자 신원 토큰 서명기 (HS256).

Design Ref: mcp-identity-header §2.3 — mcp-outlook-server 의 HmacTokenVerifier 가
HS256 만 허용한다. 알고리즘은 고정이며 호출자가 바꿀 수 없다.
"""
from jose import jwt

_ALGORITHM = "HS256"


class HmacIdentityTokenSigner:
    """클레임 조립은 도메인(IdentityClaimPolicy) 몫, 여기는 서명만 한다."""

    def sign(self, claims: dict, secret: str) -> str:
        return jwt.encode(claims, secret, algorithm=_ALGORITHM)
