"""시장 분석 접근 판정.

Design Ref: stock-analysis-agents DD10 — 권한 코드 2개 + 모듈 전용 접근 API.
Plan D5: 새 권한을 받은 사용자만 본다. admin 은 항상 열람·관리할 수 있다.

domain 은 표준 라이브러리만 쓰므로 PermissionCode
를 import 하지 않고 같은 문자열을 둔다.
두 값이 같은지는 tests/domain/market_analysis/test_access_policy.py 가 확인한다.
"""

from __future__ import annotations

from dataclasses import dataclass

VIEW_CODE = "MARKET_ANALYSIS_VIEW"
MANAGE_CODE = "MARKET_ANALYSIS_MANAGE"
ADMIN_ROLE = "admin"


@dataclass(frozen=True)
class AccessDecision:
    """GET /access 응답의 원본. enabled 는 모듈이 켜져 응답하고 있다는 뜻이다."""

    enabled: bool
    can_view: bool
    can_manage: bool


class AccessPolicy:
    @staticmethod
    def decide(*, role: str, codes: frozenset[str]) -> AccessDecision:
        if role == ADMIN_ROLE:
            return AccessDecision(enabled=True, can_view=True, can_manage=True)
        can_manage = MANAGE_CODE in codes
        # 관리 권한만 받은 사용자도 화면을 볼 수 있어야 관리할 수 있다
        can_view = can_manage or VIEW_CODE in codes
        return AccessDecision(enabled=True, can_view=can_view, can_manage=can_manage)
