"""접근 판정 — stock-analysis-agents design DD10, Plan FR-15 · SC-6.

- 열람: admin 이거나 VIEW 또는 MANAGE 보유
- 관리: admin 이거나 MANAGE 보유
"""

import pytest
from src.domain.market_analysis.access import (
    MANAGE_CODE,
    VIEW_CODE,
    AccessDecision,
    AccessPolicy,
)


def test_codes_match_permission_enum_values():
    # domain 은 permission 패키지를 import
    # 하지 않으므로 문자열을 따로 둔다 — 값이 같아야 한다
    from src.domain.permission.value_objects import PermissionCode

    assert VIEW_CODE == PermissionCode.MARKET_ANALYSIS_VIEW.value
    assert MANAGE_CODE == PermissionCode.MARKET_ANALYSIS_MANAGE.value


@pytest.mark.parametrize(
    ("role", "codes", "view", "manage"),
    [
        ("admin", frozenset(), True, True),
        ("user", frozenset(), False, False),
        ("user", frozenset({"USE_RAG_SEARCH"}), False, False),
        ("user", frozenset({VIEW_CODE}), True, False),
        ("user", frozenset({MANAGE_CODE}), True, True),
        ("user", frozenset({VIEW_CODE, MANAGE_CODE}), True, True),
        ("unknown", frozenset({VIEW_CODE}), True, False),
    ],
)
def test_decide(role, codes, view, manage):
    decision = AccessPolicy.decide(role=role, codes=codes)
    assert decision == AccessDecision(enabled=True, can_view=view, can_manage=manage)
