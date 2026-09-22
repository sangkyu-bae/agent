"""ToolCatalogRepository 단위 테스트 — AsyncMock 사용."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.infrastructure.tool_catalog.tool_catalog_repository import ToolCatalogRepository


def _make_entry(tool_id: str = "internal:tavily_search") -> ToolCatalogEntry:
    now = datetime.now(timezone.utc)
    return ToolCatalogEntry(
        id="tc-1", tool_id=tool_id, source="internal",
        name="Tavily 검색", description="웹 검색",
        created_at=now, updated_at=now,
    )


def _make_repo() -> tuple[ToolCatalogRepository, MagicMock]:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    logger = MagicMock()
    return ToolCatalogRepository(session=session, logger=logger), session


class TestToolCatalogRepositorySave:
    @pytest.mark.asyncio
    async def test_save_adds_and_flushes(self):
        repo, session = _make_repo()
        entry = _make_entry()
        result = await repo.save(entry, "req-1")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert result.tool_id == entry.tool_id


class TestToolCatalogRepositoryUpsert:
    @pytest.mark.asyncio
    async def test_upsert_inserts_when_not_exists(self):
        repo, session = _make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        entry = _make_entry()
        await repo.upsert_by_tool_id(entry, "req-1")
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_updates_when_exists(self):
        repo, session = _make_repo()
        now = datetime.now(timezone.utc)
        existing_model = MagicMock()
        existing_model.id = "tc-1"
        existing_model.tool_id = "internal:tavily_search"
        existing_model.source = "internal"
        existing_model.name = "old"
        existing_model.description = "old"
        existing_model.mcp_server_id = None
        existing_model.requires_env = None
        existing_model.is_active = True
        existing_model.created_at = now
        existing_model.updated_at = now

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                r = MagicMock()
                r.scalar_one_or_none.return_value = existing_model
                return r
            r = MagicMock()
            r.rowcount = 1
            return r

        session.execute = mock_execute

        entry = _make_entry()
        await repo.upsert_by_tool_id(entry, "req-1")
        session.add.assert_not_called()


class TestToolCatalogRepositoryBuiltin:
    @pytest.mark.asyncio
    async def test_save_carries_is_builtin(self):
        """builtin-tools D1: INSERT 경로는 entity의 is_builtin을 그대로 영속."""
        repo, session = _make_repo()
        entry = _make_entry()
        entry.is_builtin = True
        await repo.save(entry, "req-1")
        model = session.add.call_args.args[0]
        assert model.is_builtin is True

    @pytest.mark.asyncio
    async def test_upsert_update_branch_never_touches_is_builtin(self):
        """builtin-tools D2 보존 계약: UPDATE SET 절에 is_builtin이 없어야 한다.

        관리자 토글값이 부팅 sync의 upsert로 덮어써지지 않는 근거가 이 성질이므로
        테스트로 계약화한다.
        """
        repo, session = _make_repo()
        now = datetime.now(timezone.utc)
        existing_model = MagicMock()
        existing_model.id = "tc-1"
        existing_model.tool_id = "internal:wiki_read"
        existing_model.source = "internal"
        existing_model.name = "old"
        existing_model.description = "old"
        existing_model.mcp_server_id = None
        existing_model.requires_env = None
        existing_model.is_active = True
        existing_model.is_builtin = True
        existing_model.created_at = now
        existing_model.updated_at = now

        captured_stmts = []
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            captured_stmts.append(stmt)
            if call_count == 1:
                r = MagicMock()
                r.scalar_one_or_none.return_value = existing_model
                return r
            r = MagicMock()
            r.rowcount = 1
            return r

        session.execute = mock_execute

        entry = _make_entry("internal:wiki_read")
        entry.is_builtin = False  # sync가 넘기는 기본값이 와도
        await repo.upsert_by_tool_id(entry, "req-1")

        update_stmt = captured_stmts[1]
        set_columns = set(update_stmt.compile().params.keys())
        assert "is_builtin" not in set_columns

    @pytest.mark.asyncio
    async def test_set_builtin_updates_flag(self):
        """builtin-tools D3: set_builtin — is_builtin/updated_at만 UPDATE."""
        repo, session = _make_repo()
        captured_stmts = []
        call_count = 0
        now = datetime.now(timezone.utc)
        existing_model = MagicMock()
        existing_model.id = "tc-1"
        existing_model.tool_id = "internal:wiki_read"
        existing_model.source = "internal"
        existing_model.name = "위키 열람"
        existing_model.description = "d"
        existing_model.mcp_server_id = None
        existing_model.requires_env = None
        existing_model.is_active = True
        existing_model.is_builtin = True
        existing_model.created_at = now
        existing_model.updated_at = now

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            captured_stmts.append(stmt)
            r = MagicMock()
            if call_count == 1:
                r.rowcount = 1
                return r
            r.scalar_one_or_none.return_value = existing_model
            return r

        session.execute = mock_execute

        result = await repo.set_builtin("internal:wiki_read", True, "req-1")
        set_columns = set(captured_stmts[0].compile().params.keys())
        assert "is_builtin" in set_columns
        assert result is not None and result.is_builtin is True

    @pytest.mark.asyncio
    async def test_list_builtin_filters_active_and_builtin(self):
        """builtin-tools D5: 주입 대상은 is_builtin AND is_active."""
        repo, session = _make_repo()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        await repo.list_builtin("req-1")
        stmt = session.execute.call_args.args[0]
        where_sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "is_builtin" in where_sql
        assert "is_active" in where_sql


class TestToolCatalogRepositoryDeactivate:
    @pytest.mark.asyncio
    async def test_deactivate_by_mcp_server(self):
        repo, session = _make_repo()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        session.execute = AsyncMock(return_value=mock_result)

        count = await repo.deactivate_by_mcp_server("server-1", "req-1")
        assert count == 3
        session.flush.assert_awaited_once()


class TestToolCatalogRepositoryCategoryMetadata:
    """mcp-tool-category-routing §5 D-02 / FR-01·FR-03."""

    @pytest.mark.asyncio
    async def test_save_persists_category_and_limit(self):
        repo, session = _make_repo()
        entry = _make_entry("mcp:srv-1:scrape")
        entry.category = "collect"
        entry.max_tool_calls = 3

        await repo.save(entry, "req-1")

        model = session.add.call_args.args[0]
        assert model.category == "collect"
        assert model.max_tool_calls == 3

    @pytest.mark.asyncio
    async def test_save_defaults_to_unclassified(self):
        """FR-14: 지정하지 않으면 NULL — 미분류(기존 react 경로)."""
        repo, session = _make_repo()

        await repo.save(_make_entry(), "req-1")

        model = session.add.call_args.args[0]
        assert model.category is None
        assert model.max_tool_calls is None

    @pytest.mark.asyncio
    async def test_upsert_update_branch_never_touches_category(self):
        """D-02 보존 계약: UPDATE SET 절에 category/max_tool_calls가 없어야 한다.

        is_builtin과 동일한 근거 — 관리자 지정값이 부팅 sync의 upsert로
        덮어써지지 않는 성질을 SQL 수준에서 고정한다.
        """
        repo, session = _make_repo()
        now = datetime.now(timezone.utc)
        existing_model = MagicMock()
        existing_model.id = "tc-1"
        existing_model.tool_id = "mcp:srv-1:scrape"
        existing_model.source = "mcp"
        existing_model.name = "old"
        existing_model.description = "old"
        existing_model.mcp_server_id = "srv-1"
        existing_model.requires_env = None
        existing_model.is_active = True
        existing_model.is_builtin = False
        existing_model.category = "collect"
        existing_model.max_tool_calls = 3
        existing_model.created_at = now
        existing_model.updated_at = now

        captured_stmts = []
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            captured_stmts.append(stmt)
            if call_count == 1:
                r = MagicMock()
                r.scalar_one_or_none.return_value = existing_model
                return r
            r = MagicMock()
            r.rowcount = 1
            return r

        session.execute = mock_execute

        entry = _make_entry("mcp:srv-1:scrape")
        entry.category = None  # sync가 넘기는 기본값이 와도
        entry.max_tool_calls = None
        await repo.upsert_by_tool_id(entry, "req-1")

        update_stmt = captured_stmts[1]
        set_columns = set(update_stmt.compile().params.keys())
        assert "category" not in set_columns
        assert "max_tool_calls" not in set_columns

    @pytest.mark.asyncio
    async def test_to_domain_maps_category_and_limit(self):
        repo, session = _make_repo()
        now = datetime.now(timezone.utc)
        model = MagicMock()
        model.id = "tc-1"
        model.tool_id = "mcp:srv-1:scrape"
        model.source = "mcp"
        model.name = "scrape"
        model.description = "d"
        model.mcp_server_id = "srv-1"
        model.requires_env = None
        model.is_active = True
        model.is_builtin = False
        model.category = "collect"
        model.max_tool_calls = 3
        model.created_at = now
        model.updated_at = now
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        session.execute = AsyncMock(return_value=mock_result)

        entry = await repo.find_by_tool_id("mcp:srv-1:scrape", "req-1")

        assert entry.category == "collect"
        assert entry.max_tool_calls == 3


class TestToolCatalogRepositoryUpdateMetadata:
    @pytest.mark.asyncio
    async def test_update_metadata_sets_only_requested_columns(self):
        repo, session = _make_repo()
        captured_stmts = []
        call_count = 0
        now = datetime.now(timezone.utc)
        existing_model = MagicMock()
        existing_model.id = "tc-1"
        existing_model.tool_id = "mcp:srv-1:scrape"
        existing_model.source = "mcp"
        existing_model.name = "scrape"
        existing_model.description = "d"
        existing_model.mcp_server_id = "srv-1"
        existing_model.requires_env = None
        existing_model.is_active = True
        existing_model.is_builtin = False
        existing_model.category = "collect"
        existing_model.max_tool_calls = None
        existing_model.created_at = now
        existing_model.updated_at = now

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            captured_stmts.append(stmt)
            r = MagicMock()
            if call_count == 1:
                r.rowcount = 1
                return r
            r.scalar_one_or_none.return_value = existing_model
            return r

        session.execute = mock_execute

        result = await repo.update_metadata(
            "mcp:srv-1:scrape", "req-1", category="collect",
        )

        set_columns = set(captured_stmts[0].compile().params.keys())
        assert "category" in set_columns
        # max_tool_calls는 요청에 없었으므로 SET 절에 없어야 한다(부분 갱신)
        assert "max_tool_calls" not in set_columns
        assert result is not None
        assert result.category == "collect"

    @pytest.mark.asyncio
    async def test_update_metadata_can_clear_category(self):
        """None 지정은 '변경 없음'이 아니라 '미분류로 되돌리기'다."""
        repo, session = _make_repo()
        captured_stmts = []
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            captured_stmts.append(stmt)
            r = MagicMock()
            if call_count == 1:
                r.rowcount = 1
                return r
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = mock_execute

        await repo.update_metadata("mcp:srv-1:scrape", "req-1", category=None)

        set_columns = set(captured_stmts[0].compile().params.keys())
        assert "category" in set_columns

    @pytest.mark.asyncio
    async def test_update_metadata_returns_none_when_missing(self):
        repo, session = _make_repo()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.update_metadata("nope", "req-1", category="collect")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_metadata_noop_when_nothing_requested(self):
        """변경 요청이 없으면 UPDATE를 실행하지 않고 현재 상태만 반환한다."""
        repo, session = _make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        await repo.update_metadata("mcp:srv-1:scrape", "req-1")

        # 조회 1회만 — UPDATE 미실행
        assert session.execute.await_count == 1


class TestRequiresApprovalPreservation:
    """approval-gate Design §3.3 (FR-02) — is_builtin D2 와 동형의 보존 계약.

    sync(upsert) 가 관리자 토글을 덮으면 켜 둔 승인 게이트가 부팅 한 번에
    조용히 꺼진다. 보존은 '코드를 추가하지 않음' 으로 성립하므로 테스트가
    계약을 고정한다.
    """

    @pytest.mark.asyncio
    async def test_save_carries_requires_approval(self):
        repo, session = _make_repo()
        entry = _make_entry("internal:email_send")
        entry.requires_approval = True
        await repo.save(entry, "req-1")
        model = session.add.call_args[0][0]
        assert model.requires_approval is True

    @pytest.mark.asyncio
    async def test_upsert_update_branch_never_touches_requires_approval(self):
        repo, session = _make_repo()
        now = datetime.now(timezone.utc)
        existing_model = MagicMock()
        existing_model.id = "tc-1"
        existing_model.tool_id = "internal:email_send"
        existing_model.source = "internal"
        existing_model.name = "old"
        existing_model.description = "old"
        existing_model.mcp_server_id = None
        existing_model.requires_env = None
        existing_model.is_active = True
        existing_model.is_builtin = False
        existing_model.requires_approval = True  # 관리자가 켜 둔 상태
        existing_model.created_at = now
        existing_model.updated_at = now

        captured_stmts = []
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            captured_stmts.append(stmt)
            if call_count == 1:
                r = MagicMock()
                r.scalar_one_or_none.return_value = existing_model
                return r
            r = MagicMock()
            r.rowcount = 1
            return r

        session.execute = mock_execute

        entry = _make_entry("internal:email_send")
        entry.requires_approval = False  # sync 가 기본값을 넘겨도
        await repo.upsert_by_tool_id(entry, "req-1")

        update_stmt = captured_stmts[1]
        set_columns = set(update_stmt.compile().params.keys())
        assert "requires_approval" not in set_columns

    @pytest.mark.asyncio
    async def test_update_metadata_can_toggle_requires_approval(self):
        """관리자 토글의 유일한 쓰기 경로."""
        repo, session = _make_repo()
        captured_stmts = []

        async def mock_execute(stmt):
            captured_stmts.append(stmt)
            r = MagicMock()
            r.rowcount = 1
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = mock_execute
        await repo.update_metadata(
            "internal:email_send", "req-1", requires_approval=True
        )
        set_columns = set(captured_stmts[0].compile().params.keys())
        assert "requires_approval" in set_columns

    @pytest.mark.asyncio
    async def test_update_metadata_omission_does_not_touch_it(self):
        """category 만 바꿀 때 승인 플래그가 딸려 나가면 안 된다."""
        repo, session = _make_repo()
        captured_stmts = []

        async def mock_execute(stmt):
            captured_stmts.append(stmt)
            r = MagicMock()
            r.rowcount = 1
            r.scalar_one_or_none.return_value = None
            return r

        session.execute = mock_execute
        await repo.update_metadata("internal:email_send", "req-1", category="action")
        set_columns = set(captured_stmts[0].compile().params.keys())
        assert "requires_approval" not in set_columns
