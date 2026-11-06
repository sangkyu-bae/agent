"""tool-access-control module-1 — 도메인 정규화·VO·판정 정책 테스트.

Design Ref: tool-access-control §3.1 ~ §3.5
"""
import pytest

from src.domain.tool_access.exceptions import (
    ToolAccessDeniedError,
    UnknownToolIdsError,
)
from src.domain.tool_access.policy import ToolAccessPolicy
from src.domain.tool_access.tool_ids import to_catalog_tool_id
from src.domain.tool_access.value_objects import ToolAccessSet

_SRV = "7f3c0000-0000-0000-0000-000000000001"


class TestToCatalogToolId:
    """§3.2 — 판정 전 저장 표기를 카탈로그 표기로 바꾼다."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("internal_document_search", "internal:internal_document_search"),
            ("internal:excel_export", "internal:excel_export"),
            (f"mcp:{_SRV}:search", f"mcp:{_SRV}:search"),
            (f"mcp:{_SRV}:ns:tool", f"mcp:{_SRV}:ns:tool"),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert to_catalog_tool_id(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        ["", "   ", f"mcp_{_SRV}", "mcp_", "mcp:", f"mcp:{_SRV}", "internal:", None],
    )
    def test_unresolvable_returns_none(self, raw):
        # 레거시 서버 단위(mcp_{srv})는 개별 도구를 특정하지 못해 None — FR-12 별도 처리
        assert to_catalog_tool_id(raw) is None

    def test_strips_whitespace(self):
        assert to_catalog_tool_id("  excel_export ") == "internal:excel_export"


class TestToolAccessSet:
    def test_deny_all_allows_nothing(self):
        s = ToolAccessSet.deny_all()
        assert not s.is_admin
        assert not s.allows("internal:excel_export")
        assert not s.allows("excel_export")

    def test_admin_allows_everything_including_unknown(self):
        s = ToolAccessSet.admin()
        assert s.allows("internal:excel_export")
        assert s.allows(f"mcp_{_SRV}")
        assert s.allows("anything")

    def test_allows_accepts_storage_form(self):
        s = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:excel_export"}))
        assert s.allows("excel_export")
        assert s.allows("internal:excel_export")
        assert not s.allows("internal:python_code_executor")

    def test_unresolvable_id_denied_for_non_admin(self):
        s = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:excel_export"}))
        assert not s.allows("")
        assert not s.allows(f"mcp_{_SRV}")

    def test_allowed_mcp_tool_names_for_server(self):
        s = ToolAccessSet(
            is_admin=False,
            allowed=frozenset({
                f"mcp:{_SRV}:search",
                f"mcp:{_SRV}:ns:tool",
                "mcp:other-server:write",
                "internal:excel_export",
            }),
        )
        assert s.allowed_mcp_tool_names(_SRV) == frozenset({"search", "ns:tool"})
        assert s.allowed_mcp_tool_names("no-such") == frozenset()

    def test_allowed_mcp_tool_names_admin_is_none(self):
        # None = 서버 도구 전부 허용
        assert ToolAccessSet.admin().allowed_mcp_tool_names(_SRV) is None

    def test_allows_reference_individual_ids_same_as_allows(self):
        s = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:excel_export"}))
        assert s.allows_reference("excel_export")
        assert not s.allows_reference("python_code_executor")

    def test_allows_reference_server_level_needs_any_tool_on_server(self):
        # FR-12: 레거시 서버 단위 참조는 서버 도구 중 하나라도 허용이면 워커 유지
        s = ToolAccessSet(is_admin=False, allowed=frozenset({f"mcp:{_SRV}:search"}))
        assert s.allows_reference(f"mcp_{_SRV}")
        assert not s.allows_reference("mcp_other-server")
        assert not ToolAccessSet.deny_all().allows_reference(f"mcp_{_SRV}")
        assert ToolAccessSet.admin().allows_reference(f"mcp_{_SRV}")

    def test_allows_reference_garbage_denied(self):
        s = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:x"}))
        assert not s.allows_reference("")
        assert not s.allows_reference(None)

    def test_is_immutable(self):
        s = ToolAccessSet.deny_all()
        with pytest.raises(Exception):
            s.is_admin = True  # type: ignore[misc]


class TestToolAccessPolicy:
    """§3.5 판정 정책 — admin 전부, 그 외 grants 합집합만."""

    def test_admin_role_is_admin_set(self):
        s = ToolAccessPolicy.build(role="admin", grants=frozenset())
        assert s.is_admin

    def test_user_role_gets_given_grants_only(self):
        s = ToolAccessPolicy.build(
            role="user", grants=frozenset({"internal:excel_export"})
        )
        assert not s.is_admin
        assert s.allowed == frozenset({"internal:excel_export"})

    def test_anonymous_role_denied_even_with_grants(self):
        s = ToolAccessPolicy.build(
            role="anonymous", grants=frozenset({"internal:excel_export"})
        )
        assert s == ToolAccessSet.deny_all()

    def test_unknown_role_denied(self):
        s = ToolAccessPolicy.build(role="guest", grants=frozenset({"x"}))
        assert s == ToolAccessSet.deny_all()

    def test_grants_are_normalized(self):
        s = ToolAccessPolicy.build(
            role="user", grants=frozenset({"excel_export", f"mcp_{_SRV}", ""})
        )
        # 저장 표기는 카탈로그 표기로, 해석 불가 값은 버린다
        assert s.allowed == frozenset({"internal:excel_export"})


class TestExceptions:
    def test_denied_is_permission_error_with_ids(self):
        e = ToolAccessDeniedError(["b", "a", "a"])
        assert isinstance(e, PermissionError)
        assert e.tool_ids == ("a", "b")

    def test_unknown_is_value_error_with_ids(self):
        e = UnknownToolIdsError(["z", "y"])
        assert isinstance(e, ValueError)
        assert e.tool_ids == ("y", "z")
