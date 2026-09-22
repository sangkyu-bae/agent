"""AgentDefinitionRepository 단위 테스트 — AsyncMock 사용."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.infrastructure.agent_builder.agent_definition_repository import (
    AgentDefinitionRepository,
)


def _make_worker(tool_id: str = "tavily_search", sort_order: int = 0) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id,
        worker_id=f"{tool_id}_worker",
        description="테스트 워커",
        sort_order=sort_order,
    )


def _make_agent() -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()),
        user_id="user-1",
        name="테스트 에이전트",
        description="테스트 요청",
        system_prompt="테스트 프롬프트",
        flow_hint="힌트",
        workers=[_make_worker("tavily_search", 0), _make_worker("excel_export", 1)],
        llm_model_id="model-1",
        status="active",
        created_at=now,
        updated_at=now,
    )


def _make_repo() -> tuple[AgentDefinitionRepository, MagicMock]:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    logger = MagicMock()
    return AgentDefinitionRepository(session=session, logger=logger), session


class TestAgentDefinitionRepositorySave:
    @pytest.mark.asyncio
    async def test_save_adds_model_and_flushes(self):
        repo, session = _make_repo()
        agent = _make_agent()
        result = await repo.save(agent, "req-1")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert result.id == agent.id

    @pytest.mark.asyncio
    async def test_save_creates_agent_tool_rows(self):
        repo, session = _make_repo()
        agent = _make_agent()
        await repo.save(agent, "req-1")
        added_model = session.add.call_args[0][0]
        assert len(added_model.tools) == 2
        tool_ids = {t.tool_id for t in added_model.tools}
        assert tool_ids == {"tavily_search", "excel_export"}


class TestAgentDefinitionRepositoryFindById:
    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_when_not_found(self):
        repo, session = _make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await repo.find_by_id("non-existent", "req-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_id_returns_domain_object(self):
        repo, session = _make_repo()
        now = datetime.now(timezone.utc)

        mock_tool = MagicMock()
        mock_tool.tool_id = "tavily_search"
        mock_tool.worker_id = "search_worker"
        mock_tool.description = "검색"
        mock_tool.sort_order = 0
        mock_tool.tool_config = None
        mock_tool.worker_type = "tool"
        mock_tool.ref_agent_id = None
        mock_tool.category = None

        mock_model = MagicMock()
        mock_model.id = "agent-1"
        mock_model.user_id = "user-1"
        mock_model.name = "테스트"
        mock_model.description = "설명"
        mock_model.system_prompt = "프롬프트"
        mock_model.flow_hint = "힌트"
        mock_model.llm_model_id = "model-1"
        mock_model.status = "active"
        mock_model.visibility = "private"
        mock_model.department_id = None
        mock_model.temperature = 0.70
        mock_model.max_iterations = 25
        mock_model.created_at = now
        mock_model.updated_at = now
        mock_model.tools = [mock_tool]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        session.execute.return_value = mock_result

        result = await repo.find_by_id("agent-1", "req-1")
        assert isinstance(result, AgentDefinition)
        assert result.id == "agent-1"
        assert result.max_iterations == 25
        assert len(result.workers) == 1
        assert result.workers[0].tool_id == "tavily_search"


class TestAgentDefinitionRepositoryUpdate:
    @pytest.mark.asyncio
    async def test_update_modifies_system_prompt_and_name(self):
        repo, session = _make_repo()

        mock_model = MagicMock()
        mock_model.tools = []
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_model
        session.execute.return_value = mock_result

        agent = _make_agent()
        agent.system_prompt = "수정된 프롬프트"
        agent.name = "수정된 이름"
        await repo.update(agent, "req-1")

        assert mock_model.system_prompt == "수정된 프롬프트"
        assert mock_model.name == "수정된 이름"
        assert session.flush.await_count >= 1

    @pytest.mark.asyncio
    async def test_update_persists_flow_hint(self):
        """agent-update-tool-editing: 도구 재구성 시 flow_hint 도 함께 갱신된다.

        누락되면 supervisor 프롬프트가 옛 도구 체인을 계속 가리킨다.
        """
        repo, session = _make_repo()

        mock_model = MagicMock()
        mock_model.tools = []
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_model
        session.execute.return_value = mock_result

        agent = _make_agent()
        agent.flow_hint = "excel_export → wiki_read"
        await repo.update(agent, "req-1")

        assert mock_model.flow_hint == "excel_export → wiki_read"

    @pytest.mark.asyncio
    async def test_update_syncs_worker_rows(self):
        """update는 도메인 workers와 일치하도록 tool row를 재구성한다."""
        repo, session = _make_repo()

        mock_model = MagicMock()
        mock_model.tools = []
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_model
        session.execute.return_value = mock_result

        agent = _make_agent()  # 2 tool workers
        await repo.update(agent, "req-1")

        # clear() 후 workers 수만큼 append
        assert len(mock_model.tools) == 2
        tool_ids = {t.tool_id for t in mock_model.tools}
        assert tool_ids == {"tavily_search", "excel_export"}


class TestMiddlewareSyncPreservesConfig:
    """approval-gate Check G3 — 에이전트 수정이 미들웨어 설정을 지우면 안 된다.

    _sync_middleware 는 delete 후 재삽입이라 이전에는 모든 행이 config=None
    으로 다시 쓰였다. 두 가지로 막는다:
      1) 폼이 관리하는 타입은 유지되는 한 기존 config 를 옮겨 심는다.
      2) 전용 API 소유 타입(approval_gate)은 폼 동기화가 아예 건드리지 않는다.
    """

    @staticmethod
    def _existing(session, rows):
        existing = MagicMock()
        existing.scalars.return_value.all.return_value = [
            MagicMock(middleware_type=t, config=c) for t, c in rows
        ]
        session.execute = AsyncMock(return_value=existing)

    @pytest.mark.asyncio
    async def test_유지되는_폼_타입의_config는_보존된다(self):
        repo, session = _make_repo()
        self._existing(session, [("model_retry", {"max_retries": 1})])
        await repo._sync_middleware("ag1", ["model_retry"])
        added = session.add.call_args_list[0].args[0]
        assert added.config == {"max_retries": 1}

    @pytest.mark.asyncio
    async def test_빠진_폼_타입은_config와_함께_사라진다(self):
        repo, session = _make_repo()
        self._existing(session, [("model_retry", {"max_retries": 1})])
        await repo._sync_middleware("ag1", ["tool_retry"])
        added = [c.args[0].middleware_type for c in session.add.call_args_list]
        assert added == ["tool_retry"]

    @pytest.mark.asyncio
    async def test_신규_타입은_config_None(self):
        repo, session = _make_repo()
        self._existing(session, [])
        await repo._sync_middleware("ag1", ["model_retry"])
        assert session.add.call_args_list[0].args[0].config is None

    @pytest.mark.asyncio
    async def test_승인게이트는_폼_목록에_있어도_재삽입하지_않는다(self):
        """전용 API 소유 — 폼이 재삽입하면 행이 중복되거나 config 가 초기화된다."""
        repo, session = _make_repo()
        self._existing(session, [("approval_gate", {"execute_after": "0 0 * * *"})])
        await repo._sync_middleware("ag1", ["model_retry", "approval_gate"])
        added = [c.args[0].middleware_type for c in session.add.call_args_list]
        assert added == ["model_retry"]

    @pytest.mark.asyncio
    async def test_승인게이트는_폼_목록에_없어도_삭제하지_않는다(self):
        """폼 목록에서 빠졌다는 이유로 전용 API 설정이 지워지면 안 된다."""
        from sqlalchemy.dialects import mysql

        repo, session = _make_repo()
        self._existing(session, [("approval_gate", {"execute_after": "0 0 * * *"})])
        await repo._sync_middleware("ag1", ["model_retry"])
        delete_stmts = [
            c.args[0] for c in session.execute.call_args_list
            if "DELETE" in str(c.args[0].compile(dialect=mysql.dialect())).upper()
        ]
        sql = str(delete_stmts[0].compile(
            dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}
        ))
        assert "NOT IN" in sql.upper() and "approval_gate" in sql
