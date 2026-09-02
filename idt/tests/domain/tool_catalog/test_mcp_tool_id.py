"""MCP tool_id 파싱 헬퍼 단위 테스트.

카탈로그·에이전트 저장·실행이 같은 입자도(개별 도구)를 쓰도록 하는
단일 파싱 지점이다. 레거시 서버 단위 형식도 함께 해석한다.
"""
import pytest

from src.domain.tool_catalog.mcp_tool_id import McpToolRef, parse_mcp_tool_id

_UUID = "081c6fe7-e0bd-4aad-9a42-29b8bf073167"


class TestParseMcpToolId:
    def test_catalog_format_yields_server_and_tool(self):
        ref = parse_mcp_tool_id(f"mcp:{_UUID}:create_issue")
        assert ref == McpToolRef(server_id=_UUID, tool_name="create_issue")

    def test_tool_name_may_contain_colon(self):
        """도구명에 콜론이 들어가도 서버 id 뒤 전체가 도구명이다."""
        ref = parse_mcp_tool_id(f"mcp:{_UUID}:ns:create")
        assert ref == McpToolRef(server_id=_UUID, tool_name="ns:create")

    def test_legacy_server_format_yields_no_tool_name(self):
        ref = parse_mcp_tool_id(f"mcp_{_UUID}")
        assert ref == McpToolRef(server_id=_UUID, tool_name=None)

    @pytest.mark.parametrize(
        "tool_id",
        [
            "internal:tavily_search",
            "tavily_search",
            "",
            "mcp:",
            f"mcp:{_UUID}",  # 도구명 없음 — 카탈로그 형식이 아니다
            f"mcp:{_UUID}:",  # 빈 도구명
            "mcp_",
        ],
    )
    def test_non_mcp_or_malformed_returns_none(self, tool_id):
        assert parse_mcp_tool_id(tool_id) is None

    def test_is_mcp_helper_covers_both_formats(self):
        assert parse_mcp_tool_id(f"mcp:{_UUID}:x") is not None
        assert parse_mcp_tool_id(f"mcp_{_UUID}") is not None


class TestMcpToolRef:
    def test_server_level_flag(self):
        assert McpToolRef(server_id=_UUID, tool_name=None).is_server_level is True
        assert McpToolRef(server_id=_UUID, tool_name="x").is_server_level is False
