"""권한 코드 읽기 어댑터 — role 기본 권한 + 사용자 추가 권한의 합집합."""

from unittest.mock import MagicMock

from src.infrastructure.market_analysis.adapters.access import PermissionCodesReader


class FakePermissionRepo:
    def __init__(
        self, role_codes: dict[str, list[str]], user_codes: dict[int, list[str]]
    ):
        self.role_codes = role_codes
        self.user_codes = user_codes

    async def find_codes_for_role(self, role: str, request_id: str) -> list[str]:
        return self.role_codes.get(role, [])

    async def find_codes_for_user(self, user_id: int, request_id: str) -> list[str]:
        return self.user_codes.get(user_id, [])


async def test_union_of_role_and_user_codes():
    repo = FakePermissionRepo(
        {"user": ["USE_RAG_SEARCH"]}, {7: ["MARKET_ANALYSIS_VIEW"]}
    )
    reader = PermissionCodesReader(repo, MagicMock())
    assert await reader.codes_for(7, "user", "r") == frozenset(
        {"USE_RAG_SEARCH", "MARKET_ANALYSIS_VIEW"}
    )


async def test_user_without_grants():
    reader = PermissionCodesReader(FakePermissionRepo({}, {}), MagicMock())
    assert await reader.codes_for(9, "user", "r") == frozenset()
