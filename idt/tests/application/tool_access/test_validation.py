"""저장·포크 공용 판정 모듈 테스트.

Design Ref: tool-access-control §2.2 (저장 = 신규분만 검증, 포크 = 제외 복제), §3.2
"""
import pytest

from src.application.tool_access.validation import (
    ensure_new_tools_allowed,
    excluded_info,
    partition_tool_workers,
    tool_display_name,
)
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.tool_access.exceptions import ToolAccessDeniedError
from src.domain.tool_access.value_objects import ToolAccessSet

SRV = "7f3c0000-0000-0000-0000-000000000001"
ACCESS = ToolAccessSet(
    is_admin=False,
    allowed=frozenset({"internal:excel_export", f"mcp:{SRV}:search"}),
)


def _w(tool_id: str, worker_type: str = "tool") -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id, worker_id=f"{tool_id}_w", description="",
        worker_type=worker_type, ref_agent_id="a1" if worker_type == "sub_agent" else None,
    )


class TestEnsureNewToolsAllowed:
    def test_all_allowed_passes(self):
        ensure_new_tools_allowed(ACCESS, ["excel_export", f"mcp:{SRV}:search"])

    def test_denied_new_tool_raises_with_catalog_ids(self):
        with pytest.raises(ToolAccessDeniedError) as ei:
            ensure_new_tools_allowed(ACCESS, ["excel_export", "python_code_executor"])
        assert ei.value.tool_ids == ("internal:python_code_executor",)

    def test_previous_tools_are_not_checked(self):
        # 결정: 기존에 붙어 있던 도구는 권한과 무관하게 유지 저장 (FR-06)
        ensure_new_tools_allowed(
            ACCESS, ["excel_export", "python_code_executor"],
            previous_tool_ids=["python_code_executor"],
        )

    def test_previous_matches_across_namespaces(self):
        ensure_new_tools_allowed(
            ACCESS, ["internal:python_code_executor"],
            previous_tool_ids=["python_code_executor"],
        )

    def test_legacy_server_level_reference(self):
        ensure_new_tools_allowed(ACCESS, [f"mcp_{SRV}"])
        with pytest.raises(ToolAccessDeniedError) as ei:
            ensure_new_tools_allowed(ACCESS, ["mcp_other"])
        assert ei.value.tool_ids == ("mcp_other",)

    def test_admin_passes_everything(self):
        ensure_new_tools_allowed(ToolAccessSet.admin(), ["anything", "mcp_x"])

    def test_deny_all_blocks_everything_new(self):
        with pytest.raises(ToolAccessDeniedError):
            ensure_new_tools_allowed(ToolAccessSet.deny_all(), ["excel_export"])
        ensure_new_tools_allowed(ToolAccessSet.deny_all(), [])


class TestPartitionToolWorkers:
    def test_splits_tool_workers_and_keeps_sub_agents(self):
        workers = [_w("excel_export"), _w("python_code_executor"), _w("", "sub_agent")]
        kept, excluded = partition_tool_workers(ACCESS, workers)
        assert [w.tool_id for w in kept] == ["excel_export", ""]
        assert [w.tool_id for w in excluded] == ["python_code_executor"]

    def test_keep_ids_preserve_previous(self):
        kept, excluded = partition_tool_workers(
            ACCESS, [_w("python_code_executor")], keep_tool_ids=["internal:python_code_executor"]
        )
        assert [w.tool_id for w in kept] == ["python_code_executor"]
        assert excluded == []

    def test_preserves_order(self):
        workers = [_w("python_code_executor"), _w("excel_export"), _w(f"mcp:{SRV}:search")]
        kept, _ = partition_tool_workers(ACCESS, workers)
        assert [w.tool_id for w in kept] == ["excel_export", f"mcp:{SRV}:search"]


class TestDisplayName:
    def test_catalog_name_wins(self):
        names = {"internal:excel_export": "엑셀 만들기"}
        assert tool_display_name("excel_export", names) == "엑셀 만들기"

    def test_registry_name_for_internal(self):
        assert tool_display_name("excel_export") == "Excel 파일 생성"

    def test_mcp_tool_segment(self):
        assert tool_display_name(f"mcp:{SRV}:ns:write_ticket") == "ns:write_ticket"

    def test_unknown_falls_back_to_raw(self):
        assert tool_display_name("mcp_xyz") == "mcp_xyz"
        assert tool_display_name("no_such_tool") == "no_such_tool"

    def test_notice_lists_names_only(self):
        from src.application.tool_access.validation import excluded_tools_notice

        text = excluded_tools_notice([_w("python_code_executor"), _w(f"mcp:{SRV}:write")])
        assert "Python 코드 실행" in text and "write" in text
        assert SRV not in text  # 서버 id 비노출
        assert "internal:" not in text
        assert excluded_tools_notice([]) == ""

    def test_excluded_info(self):
        info = excluded_info([_w("python_code_executor")])
        assert len(info) == 1
        assert info[0].tool_id == "internal:python_code_executor"
        assert info[0].name == "Python 코드 실행"
        assert info[0].reason == "no_permission"
