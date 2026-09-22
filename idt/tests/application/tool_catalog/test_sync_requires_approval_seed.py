"""MCP 서버 플래그 → 신규 카탈로그 엔트리의 requires_approval 초기값.

Design Ref: approval-gate-phase2-mcp-executor §3, §8.2 (S1~S4), D-07.

MCP 서버는 사용자별로 등록되고 sync 는 등록 건마다 엔트리를 만든다. 초기값이
항상 False 면 새 BYO 사용자의 발송 도구는 관리자가 찾아서 켜기 전까지 승인
없이 실행된다 (fail-open). 서버 등록의 플래그가 그 초기값을 정한다.

보존 계약은 그대로다 — 플래그는 신규 INSERT 에만 쓰이고, 기존 엔트리의 값은
sync 가 건드리지 않는다. UPDATE 분기의 SQL 수준 보증은
tests/infrastructure/tool_catalog/test_tool_catalog_repository.py 의
`test_upsert_update_branch_never_touches_requires_approval` 가 맡는다.
"""
from unittest.mock import AsyncMock, MagicMock

from src.application.tool_catalog.sync_mcp_tools_use_case import SyncMcpToolsUseCase
from src.domain.tool_catalog.entity import ToolCatalogEntry


class FakeToolCatalogRepo:
    """실제 upsert 계약 모사 — INSERT 만 requires_approval 을 영속한다."""

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
                id=entry.id, tool_id=entry.tool_id, source=entry.source,
                name=entry.name, description=entry.description,
                mcp_server_id=entry.mcp_server_id, is_active=entry.is_active,
                requires_approval=entry.requires_approval,
            )
        else:
            existing.name = entry.name
            existing.description = entry.description
            existing.is_active = entry.is_active
        return self.rows[entry.tool_id]

    async def deactivate_by_mcp_server(self, server_id: str, request_id: str) -> int:
        return 0


def _server(flag: bool, server_id: str = "srv-1"):
    server = MagicMock()
    server.id = server_id
    server.is_active = True
    server.default_requires_approval = flag
    return server


def _tool(name: str):
    tool = MagicMock()
    tool.mcp_tool_name = name
    tool.description = f"{name} 도구"
    return tool


def _use_case(repo: FakeToolCatalogRepo, server, tools):
    server_repo = MagicMock()
    server_repo.find_all_active = AsyncMock(return_value=[server])
    loader = MagicMock()
    loader.load = AsyncMock(return_value=tools)
    return SyncMcpToolsUseCase(
        tool_catalog_repo=repo, mcp_server_repo=server_repo,
        mcp_tool_loader=loader, logger=MagicMock(),
    )


class TestSeedFromServerFlag:
    async def test_플래그가_켜진_서버의_새_도구는_승인_대상으로_시작한다(self):
        """Plan SC-5."""
        repo = FakeToolCatalogRepo()
        uc = _use_case(repo, _server(True), [_tool("send_email"), _tool("read_mail")])
        await uc.execute(None, "req-1")
        assert len(repo.rows) == 2
        assert all(row.requires_approval is True for row in repo.rows.values())

    async def test_플래그가_꺼진_서버는_기존과_같다(self):
        """무회귀 — 기존 서버(기본 0)의 동작은 변하지 않는다."""
        repo = FakeToolCatalogRepo()
        uc = _use_case(repo, _server(False), [_tool("scrape")])
        await uc.execute(None, "req-1")
        assert repo.rows["mcp:srv-1:scrape"].requires_approval is False


class TestAdminValueSurvives:
    """Plan SC-6 — 플래그는 초기값일 뿐, 런타임 SoT 는 카탈로그다."""

    async def test_관리자가_끈_값은_플래그가_켜져_있어도_유지된다(self):
        repo = FakeToolCatalogRepo()
        uc = _use_case(repo, _server(True), [_tool("read_mail")])
        await uc.execute(None, "req-1")
        repo.rows["mcp:srv-1:read_mail"].requires_approval = False  # 관리자 해제

        await uc.execute(None, "req-2")

        assert repo.rows["mcp:srv-1:read_mail"].requires_approval is False

    async def test_관리자가_켠_값은_플래그가_꺼져_있어도_유지된다(self):
        repo = FakeToolCatalogRepo()
        uc = _use_case(repo, _server(False), [_tool("send_email")])
        await uc.execute(None, "req-1")
        repo.rows["mcp:srv-1:send_email"].requires_approval = True  # 관리자 지정

        await uc.execute(None, "req-2")

        assert repo.rows["mcp:srv-1:send_email"].requires_approval is True

    async def test_플래그를_나중에_켜도_기존_도구에는_소급하지_않는다(self):
        """FR-16 — 그 사이 서버에 새로 생긴 도구만 새 값을 받는다."""
        repo = FakeToolCatalogRepo()
        await _use_case(repo, _server(False), [_tool("old_tool")]).execute(
            None, "req-1"
        )
        await _use_case(
            repo, _server(True), [_tool("old_tool"), _tool("new_tool")]
        ).execute(None, "req-2")

        assert repo.rows["mcp:srv-1:old_tool"].requires_approval is False
        assert repo.rows["mcp:srv-1:new_tool"].requires_approval is True
