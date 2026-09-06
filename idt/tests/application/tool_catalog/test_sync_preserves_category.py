"""sync 반복 시 category / max_tool_calls 보존 회귀 테스트.

Design Ref: mcp-tool-category-routing §5 D-02 (FR-03)
  관리자가 지정한 분류·호출 상한은 도구 카탈로그 sync가 반복 실행돼도
  덮어써지지 않아야 한다. is_builtin과 동일한 보존 계약이며, 성립 조건도 같다.

  ① Sync UseCase가 넘기는 entry가 관리자 값을 참칭하지 않는다 (기본 None)
  ② ToolCatalogRepository.upsert_by_tool_id의 UPDATE 분기가
     category / max_tool_calls를 SET하지 않는다

  ②는 tests/infrastructure/tool_catalog/test_tool_catalog_repository.py의
  `test_upsert_update_branch_never_touches_category`가 SQL 수준에서 고정한다.
  이 파일은 ①과 두 조건을 합친 결과(반복 sync 후에도 값 유지)를 고정한다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.tool_catalog.sync_mcp_tools_use_case import SyncMcpToolsUseCase
from src.domain.tool_catalog.entity import ToolCatalogEntry


class FakeToolCatalogRepo:
    """실제 upsert 계약을 모사 — UPDATE 분기는 관리자 지정 필드를 건드리지 않는다."""

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
                category=entry.category,
                max_tool_calls=entry.max_tool_calls,
            )
        else:
            # UPDATE: name/description/is_active만 —
            # is_builtin / category / max_tool_calls 제외
            existing.name = entry.name
            existing.description = entry.description
            existing.is_active = entry.is_active
        return self.rows[entry.tool_id]

    async def deactivate_by_mcp_server(self, server_id: str, request_id: str) -> int:
        return 0


def _make_server(server_id: str = "srv-1"):
    server = MagicMock()
    server.id = server_id
    server.is_active = True
    return server


def _make_tool(name: str = "scrape", description: str = "웹 페이지 수집"):
    tool = MagicMock()
    tool.mcp_tool_name = name
    tool.description = description
    return tool


def _make_use_case(repo: FakeToolCatalogRepo, server, tools):
    server_repo = MagicMock()
    server_repo.find_all_active = AsyncMock(return_value=[server])
    loader = MagicMock()
    loader.load = AsyncMock(return_value=tools)
    return SyncMcpToolsUseCase(
        tool_catalog_repo=repo,
        mcp_server_repo=server_repo,
        mcp_tool_loader=loader,
        logger=MagicMock(),
    )


class TestSyncPreservesAdminMetadata:
    @pytest.mark.asyncio
    async def test_sync_entry_does_not_claim_category(self):
        """조건 ①: sync가 만드는 entry의 category/max_tool_calls는 None이어야 한다."""
        repo = FakeToolCatalogRepo()
        uc = _make_use_case(repo, _make_server(), [_make_tool()])

        await uc.execute(None, "req-1")

        assert repo.upsert_calls, "upsert가 한 번은 호출되어야 한다"
        for entry in repo.upsert_calls:
            assert entry.category is None
            assert entry.max_tool_calls is None

    @pytest.mark.asyncio
    async def test_admin_category_survives_repeated_sync(self):
        """조건 ①+②: 관리자 지정 후 sync를 반복해도 값이 유지된다 (FR-03)."""
        repo = FakeToolCatalogRepo()
        server = _make_server()
        uc = _make_use_case(repo, server, [_make_tool()])

        await uc.execute(None, "req-1")

        tool_id = f"mcp:{server.id}:scrape"
        # 관리자가 화면에서 분류·상한을 지정한 상태를 재현
        repo.rows[tool_id].category = "collect"
        repo.rows[tool_id].max_tool_calls = 3

        # 서버 재기동·도구 재등록 등으로 sync가 여러 번 더 돈다
        await uc.execute(None, "req-2")
        await uc.execute(None, "req-3")

        assert repo.rows[tool_id].category == "collect"
        assert repo.rows[tool_id].max_tool_calls == 3

    @pytest.mark.asyncio
    async def test_description_still_updates_on_resync(self):
        """보존이 '아무것도 갱신하지 않음'을 뜻하지는 않는다 — 설명은 갱신된다."""
        repo = FakeToolCatalogRepo()
        server = _make_server()
        uc = _make_use_case(repo, server, [_make_tool(description="old")])
        await uc.execute(None, "req-1")

        tool_id = f"mcp:{server.id}:scrape"
        repo.rows[tool_id].category = "collect"

        uc2 = _make_use_case(repo, server, [_make_tool(description="new")])
        await uc2.execute(None, "req-2")

        assert repo.rows[tool_id].description == "new"
        assert repo.rows[tool_id].category == "collect"
