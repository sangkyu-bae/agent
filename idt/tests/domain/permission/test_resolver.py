"""PermissionResolver 단위 테스트 (mock 금지).

agent-user-context Design §3.3 검증:
- role + user 권한 합집합
- 중복 제거
- frozenset 반환 (immutable)
"""
import pytest

from src.domain.permission.resolver import PermissionResolver


class TestPermissionResolverResolve:
    def test_empty_inputs_return_empty_frozenset(self):
        result = PermissionResolver.resolve([], [])
        assert result == frozenset()
        assert isinstance(result, frozenset)

    def test_role_only_returns_role_codes(self):
        result = PermissionResolver.resolve(
            role_codes=["READ_PUBLIC_DOCS", "USE_RAG_SEARCH"],
            user_codes=[],
        )
        assert result == frozenset({"READ_PUBLIC_DOCS", "USE_RAG_SEARCH"})

    def test_user_only_returns_user_codes(self):
        result = PermissionResolver.resolve(
            role_codes=[],
            user_codes=["MANAGE_USERS"],
        )
        assert result == frozenset({"MANAGE_USERS"})

    def test_union_of_role_and_user(self):
        result = PermissionResolver.resolve(
            role_codes=["READ_PUBLIC_DOCS"],
            user_codes=["MANAGE_USERS"],
        )
        assert result == frozenset({"READ_PUBLIC_DOCS", "MANAGE_USERS"})

    def test_duplicates_removed(self):
        """role과 user에 같은 코드가 있어도 한 번만 포함."""
        result = PermissionResolver.resolve(
            role_codes=["USE_RAG_SEARCH"],
            user_codes=["USE_RAG_SEARCH"],
        )
        assert result == frozenset({"USE_RAG_SEARCH"})
        assert len(result) == 1

    def test_returns_immutable_frozenset(self):
        result = PermissionResolver.resolve(["A"], ["B"])
        with pytest.raises(AttributeError):
            result.add("C")  # type: ignore[attr-defined]
