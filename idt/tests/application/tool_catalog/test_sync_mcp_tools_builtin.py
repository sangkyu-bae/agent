"""MCP sync 반복 시 is_builtin 보존 회귀 테스트.

Plan Ref: mcp-tool-auto-sync R-04 / Analysis G-03
  등록·수정마다 sync가 자동 실행되면서 sync 호출 빈도가 늘었다. 관리자가 토글한
  `tool_catalog.is_builtin` 값이 반복 sync에 덮어써지지 않아야 한다.

builtin-tools D2가 그 근거이며, 실제 보존은 두 조건이 함께 성립할 때만 성립한다.
  ① SyncMcpToolsUseCase가 넘기는 entry의 is_builtin이 관리자 값을 참칭하지 않는다
  ② ToolCatalogRepository.upsert_by_tool_id의 UPDATE 분기가 is_builtin을 SET하지 않는다

②는 tests/infrastructure/tool_catalog/test_tool_catalog_repository.py의
`test_upsert_update_branch_never_touches_is_builtin`이 SQL 수준에서 고정한다.
이 파일은 ①과, 두 조건을 합친 결과(반복 sync 후에도 값 유지)를 고정한다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.tool_catalog.sync_mcp_tools_use_case import SyncMcpToolsUseCase
from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.infrastructure.mcp_registry.mcp_tool_loader import MCPToolLoader


class FakeToolCatalogRepo:
    """실제 ToolCatalogRepository의 upsert 계약을 모사하는 인메모리 저장소.

    핵심: UPDATE 분기는 is_builtin을 **건드리지 않는다**(builtin-tools D2).
    INSERT 분기만 entry의 is_builtin을 영속한다(D1).
    """

    def __init__(self) -> None:
        self.rows: dict[str, ToolCatalogEntry] = {}
        self.upsert_calls: list[ToolCatalogEntry] = []

    async def upsert_by_tool_id(
        self, entry: ToolCatalogEntry, request_id: str
    ) -> ToolCatalogEntry:
        self.upsert_calls.append(entry)
        existing = self.rows.get(entry.tool_id)
        if existing is None:
            self.rows[entry.tool_id] = ToolCatalogEntry(
                id=entry.id,
                tool_id=entry.tool_id,
                source=entry.source,
                name=entry.name,
                description=entry.description,
                mcp_server_id=entry.mcp_server_id,
                requires_env=list(entry.requires_env),
                is_active=entry.is_active,
                is_builtin=entry.is_builtin,
            )
        else:
            # UPDATE: name/description/is_active/updated_at만 — is_builtin 제외
            existing.name = entry.name
            existing.description = entry.description
            existing.is_active = entry.is_active
        return self.rows[entry.tool_id]

    async def deactivate_by_mcp_server(self, server_id: str, request_id: str) -> int:
        count = 0
        for row in self.rows.values():
            if row.mcp_server_id == server_id and row.is_active:
                row.is_active = False
                count += 1
        return count


def _make_use_case(catalog_repo, tool_names=("search",)):
    server = MagicMock()
    server.id = "srv-1"
    server.is_active = True

    mcp_server_repo = MagicMock()
    mcp_server_repo.find_by_id = AsyncMock(return_value=server)
    mcp_server_repo.find_all_active = AsyncMock(return_value=[server])

    tools = []
    for name in tool_names:
        t = MagicMock()
        t.name = f"mcp_srv_1_{name}"  # 어댑터가 붙이는 접두사 형태
        t.mcp_tool_name = name
        t.description = f"{name} 설명"
        tools.append(t)

    loader = MagicMock(spec=MCPToolLoader)
    loader.load = AsyncMock(return_value=tools)

    return SyncMcpToolsUseCase(
        tool_catalog_repo=catalog_repo,
        mcp_server_repo=mcp_server_repo,
        mcp_tool_loader=loader,
        logger=MagicMock(),
    )


class TestSyncPreservesIsBuiltin:
    @pytest.mark.asyncio
    async def test_sync_never_claims_builtin_on_upsert(self):
        """① sync가 넘기는 entry는 is_builtin을 참칭하지 않는다(기본 False)."""
        repo = FakeToolCatalogRepo()
        uc = _make_use_case(repo)

        await uc.execute("srv-1", "req-1")

        assert repo.upsert_calls, "upsert가 호출되지 않았다"
        for entry in repo.upsert_calls:
            assert entry.is_builtin is False, (
                f"{entry.tool_id}: sync가 is_builtin을 True로 넘기면 "
                "관리자 토글과 무관하게 빌트인이 켜질 수 있다"
            )

    @pytest.mark.asyncio
    async def test_admin_toggle_survives_repeated_sync(self):
        """R-04 본체: 관리자가 켠 is_builtin이 반복 sync 후에도 유지된다."""
        repo = FakeToolCatalogRepo()
        uc = _make_use_case(repo)

        # 1) 최초 sync — 행 생성 (is_builtin=False)
        await uc.execute("srv-1", "req-1")
        tool_id = "mcp:srv-1:search"
        assert repo.rows[tool_id].is_builtin is False

        # 2) 관리자가 빌트인으로 토글 (SetBuiltinToolUseCase 경로 모사)
        repo.rows[tool_id].is_builtin = True

        # 3) 등록/수정이 반복되며 sync가 여러 번 더 실행된다
        await uc.execute("srv-1", "req-2")
        await uc.execute("srv-1", "req-3")

        assert repo.rows[tool_id].is_builtin is True, (
            "반복 sync가 관리자 토글값을 덮어썼다 — builtin-tools D2 보존 계약 위반"
        )

    @pytest.mark.asyncio
    async def test_sync_still_updates_name_and_description(self):
        """보존이 '아무것도 갱신하지 않음'을 뜻하지 않는다 — 메타는 갱신된다."""
        repo = FakeToolCatalogRepo()
        uc = _make_use_case(repo)
        await uc.execute("srv-1", "req-1")

        tool_id = "mcp:srv-1:search"
        repo.rows[tool_id].is_builtin = True
        repo.rows[tool_id].name = "예전 이름"

        await uc.execute("srv-1", "req-2")

        assert repo.rows[tool_id].name == "search"       # 갱신됨
        assert repo.rows[tool_id].is_builtin is True     # 보존됨

    @pytest.mark.asyncio
    async def test_multiple_tools_all_preserve_builtin(self):
        """서버가 도구 여러 개를 노출해도 각 행의 토글이 개별 보존된다."""
        repo = FakeToolCatalogRepo()
        uc = _make_use_case(repo, tool_names=("search", "fetch", "summarize"))

        await uc.execute("srv-1", "req-1")
        repo.rows["mcp:srv-1:search"].is_builtin = True
        repo.rows["mcp:srv-1:summarize"].is_builtin = True

        await uc.execute("srv-1", "req-2")

        assert repo.rows["mcp:srv-1:search"].is_builtin is True
        assert repo.rows["mcp:srv-1:fetch"].is_builtin is False
        assert repo.rows["mcp:srv-1:summarize"].is_builtin is True
