"""DeleteAgentUseCase 단위 테스트 — Mock 의존성."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.delete_agent_use_case import DeleteAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition


NOW = datetime.now(timezone.utc)


def _make_agent(user_id: str = "user-1") -> AgentDefinition:
    return AgentDefinition(
        id="agent-1", user_id=user_id, name="에이전트",
        description="설명", system_prompt="프롬프트", flow_hint="힌트",
        workers=[WorkerDefinition(tool_id="t", worker_id="w", description="d")],
        llm_model_id="m", status="active",
        visibility="private", temperature=0.7,
        created_at=NOW, updated_at=NOW,
    )


def _make_uc():
    repo = MagicMock()
    repo.find_by_id = AsyncMock()
    repo.soft_delete = AsyncMock()
    logger = MagicMock()
    return DeleteAgentUseCase(repository=repo, logger=logger), repo


class TestDeleteAgentUseCase:
    @pytest.mark.asyncio
    async def test_owner_can_delete(self):
        uc, repo = _make_uc()
        repo.find_by_id = AsyncMock(return_value=_make_agent("user-1"))
        await uc.execute("agent-1", "user-1", "user", "req-1")
        repo.soft_delete.assert_awaited_once_with("agent-1", "req-1")

    @pytest.mark.asyncio
    async def test_admin_can_delete(self):
        uc, repo = _make_uc()
        repo.find_by_id = AsyncMock(return_value=_make_agent("user-1"))
        await uc.execute("agent-1", "user-2", "admin", "req-1")
        repo.soft_delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_owner_non_admin_forbidden(self):
        uc, repo = _make_uc()
        repo.find_by_id = AsyncMock(return_value=_make_agent("user-1"))
        with pytest.raises(PermissionError, match="삭제 권한"):
            await uc.execute("agent-1", "user-2", "user", "req-1")

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        uc, repo = _make_uc()
        repo.find_by_id = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("agent-x", "user-1", "user", "req-1")
