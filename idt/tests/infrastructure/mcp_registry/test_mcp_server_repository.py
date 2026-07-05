"""Infrastructure 테스트: MCPServerRepository (Mock AsyncSession)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.infrastructure.mcp_registry.mcp_server_repository import MCPServerRepository


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_logger():
    return MagicMock()


@pytest.fixture
def sample_entity():
    return MCPServerRegistration(
        id="uuid-001",
        user_id="user-1",
        name="Test MCP",
        description="Test description",
        endpoint="https://mcp.example.com/sse",
        transport=MCPTransportType.SSE,
        input_schema=None,
        is_active=True,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


class TestMCPServerRepositorySave:

    @pytest.mark.asyncio
    async def test_save_calls_base_repository(self, mock_session, mock_logger, sample_entity):
        repo = MCPServerRepository(session=mock_session, logger=mock_logger)
        with patch.object(repo, "_base_save", new_callable=AsyncMock) as mock_base:
            from src.infrastructure.mcp_registry.models import MCPServerModel
            mock_model = MagicMock(spec=MCPServerModel)
            mock_model.id = "uuid-001"
            mock_model.user_id = "user-1"
            mock_model.name = "Test MCP"
            mock_model.description = "Test description"
            mock_model.endpoint = "https://mcp.example.com/sse"
            mock_model.transport = "sse"
            mock_model.input_schema = None
            mock_model.is_active = True
            mock_model.created_at = datetime(2026, 1, 1)
            mock_model.updated_at = datetime(2026, 1, 1)
            mock_base.return_value = mock_model

            result = await repo.save(sample_entity, "req-001")

        assert result.id == "uuid-001"
        assert result.tool_id == "mcp_uuid-001"


class TestMCPServerRepositoryUpdate:

    @pytest.mark.asyncio
    async def test_update_uses_session_merge_not_insert(
        self, mock_session, mock_logger, sample_entity
    ):
        """update는 새 INSERT(add)가 아니라 session.merge(UPSERT)로 저장해야 한다.

        기존 PK로 add→flush 하면 중복 PK INSERT가 발생(IntegrityError 1062).
        merge는 PK 기준으로 기존 행을 찾아 UPDATE 한다.
        """
        repo = MCPServerRepository(session=mock_session, logger=mock_logger)
        from src.infrastructure.mcp_registry.models import MCPServerModel

        merged_model = MagicMock(spec=MCPServerModel)
        merged_model.id = "uuid-001"
        merged_model.user_id = "user-1"
        merged_model.name = "Test MCP"
        merged_model.description = "Test description"
        merged_model.endpoint = "https://mcp.example.com/sse"
        merged_model.transport = "sse"
        merged_model.input_schema = None
        merged_model.is_active = True
        merged_model.created_at = datetime(2026, 1, 1)
        merged_model.updated_at = datetime(2026, 1, 1)
        merged_model.auth_config_enc = None
        merged_model.server_config_enc = None
        mock_session.merge = AsyncMock(return_value=merged_model)
        mock_session.add = MagicMock()

        result = await repo.update(sample_entity, "req-001")

        mock_session.merge.assert_awaited_once()
        mock_session.flush.assert_awaited()
        mock_session.add.assert_not_called()
        assert result.id == "uuid-001"


class TestMCPServerRepositoryFindAllActive:

    @pytest.mark.asyncio
    async def test_find_all_active_returns_only_active(self, mock_session, mock_logger):
        repo = MCPServerRepository(session=mock_session, logger=mock_logger)
        with patch.object(repo, "_base_find_by_conditions", new_callable=AsyncMock) as mock_find:
            from src.infrastructure.mcp_registry.models import MCPServerModel
            mock_model = MagicMock(spec=MCPServerModel)
            mock_model.id = "uuid-001"
            mock_model.user_id = "user-1"
            mock_model.name = "Active Tool"
            mock_model.description = "desc"
            mock_model.endpoint = "https://a.com/sse"
            mock_model.transport = "sse"
            mock_model.input_schema = None
            mock_model.is_active = True
            mock_model.created_at = datetime(2026, 1, 1)
            mock_model.updated_at = datetime(2026, 1, 1)
            mock_find.return_value = [mock_model]

            result = await repo.find_all_active("req-001")

        assert len(result) == 1
        assert result[0].is_active is True

    @pytest.mark.asyncio
    async def test_find_all_active_returns_empty_list(self, mock_session, mock_logger):
        repo = MCPServerRepository(session=mock_session, logger=mock_logger)
        with patch.object(repo, "_base_find_by_conditions", new_callable=AsyncMock) as mock_find:
            mock_find.return_value = []
            result = await repo.find_all_active("req-001")
        assert result == []


class TestMCPServerRepositoryFindByUser:

    @pytest.mark.asyncio
    async def test_find_by_user_filters_by_user_id(self, mock_session, mock_logger):
        repo = MCPServerRepository(session=mock_session, logger=mock_logger)
        with patch.object(repo, "_base_find_by_conditions", new_callable=AsyncMock) as mock_find:
            from src.infrastructure.mcp_registry.models import MCPServerModel
            mock_model = MagicMock(spec=MCPServerModel)
            mock_model.id = "uuid-002"
            mock_model.user_id = "user-2"
            mock_model.name = "User Tool"
            mock_model.description = "desc"
            mock_model.endpoint = "https://b.com/sse"
            mock_model.transport = "sse"
            mock_model.input_schema = None
            mock_model.is_active = True
            mock_model.created_at = datetime(2026, 1, 1)
            mock_model.updated_at = datetime(2026, 1, 1)
            mock_find.return_value = [mock_model]

            result = await repo.find_by_user("user-2", "req-001")

        assert len(result) == 1
        assert result[0].user_id == "user-2"


class TestMCPServerRepositoryDelete:

    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self, mock_session, mock_logger):
        repo = MCPServerRepository(session=mock_session, logger=mock_logger)
        with patch.object(repo, "_base_delete", new_callable=AsyncMock) as mock_del:
            mock_del.return_value = True
            result = await repo.delete("uuid-001", "req-001")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self, mock_session, mock_logger):
        repo = MCPServerRepository(session=mock_session, logger=mock_logger)
        with patch.object(repo, "_base_delete", new_callable=AsyncMock) as mock_del:
            mock_del.return_value = False
            result = await repo.delete("not-exist", "req-001")
        assert result is False
