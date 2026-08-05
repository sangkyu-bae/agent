"""UpdateAgentUseCase middleware_types 편집 — builtin-middleware D5 (4곳 세트)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.schemas import UpdateAgentRequest
from src.application.agent_builder.update_agent_use_case import UpdateAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.middleware.entities import MiddlewareCatalogEntry, MiddlewareType


def _agent() -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id="agent-1", user_id="user-1", name="에이전트", description="d",
        system_prompt="지침", flow_hint="", workers=[],
        llm_model_id="m-1", status="active", created_at=now, updated_at=now,
    )


def _catalog() -> list[MiddlewareCatalogEntry]:
    return [
        MiddlewareCatalogEntry(
            id=f"mc-{t.value}", middleware_type=t, name=t.value, description="",
        )
        for t in (MiddlewareType.MODEL_RETRY, MiddlewareType.TOOL_RETRY)
    ]


def _uc(with_catalog: bool = True):
    repository = MagicMock()
    repository.find_by_id = AsyncMock(return_value=_agent())
    repository.update = AsyncMock(side_effect=lambda agent, rid: agent)
    catalog_repo = None
    if with_catalog:
        catalog_repo = MagicMock()
        catalog_repo.list_all = AsyncMock(return_value=_catalog())
    uc = UpdateAgentUseCase(
        repository=repository,
        perm_repo=MagicMock(),
        logger=MagicMock(),
        middleware_catalog_repo=catalog_repo,
    )
    return uc, repository


class TestUpdateMiddlewareTypes:
    @pytest.mark.asyncio
    async def test_전체_교체(self):
        uc, repository = _uc()
        await uc.execute(
            "agent-1",
            UpdateAgentRequest(middleware_types=["model_retry"]),
            "req-1",
        )
        agent = repository.update.call_args.args[0]
        assert agent.middleware_types == ["model_retry"]

    @pytest.mark.asyncio
    async def test_빈_리스트는_전부_해제(self):
        uc, repository = _uc()
        await uc.execute(
            "agent-1", UpdateAgentRequest(middleware_types=[]), "req-1"
        )
        agent = repository.update.call_args.args[0]
        assert agent.middleware_types == []

    @pytest.mark.asyncio
    async def test_None이면_미변경(self):
        uc, repository = _uc()
        await uc.execute("agent-1", UpdateAgentRequest(name="새이름"), "req-1")
        agent = repository.update.call_args.args[0]
        assert agent.middleware_types is None

    @pytest.mark.asyncio
    async def test_미지_타입은_ValueError(self):
        uc, _ = _uc()
        with pytest.raises(ValueError):
            await uc.execute(
                "agent-1",
                UpdateAgentRequest(middleware_types=["없는타입"]),
                "req-1",
            )

    @pytest.mark.asyncio
    async def test_중복은_순서_보존_dedupe(self):
        uc, repository = _uc()
        await uc.execute(
            "agent-1",
            UpdateAgentRequest(
                middleware_types=["tool_retry", "model_retry", "tool_retry"]
            ),
            "req-1",
        )
        agent = repository.update.call_args.args[0]
        assert agent.middleware_types == ["tool_retry", "model_retry"]

    @pytest.mark.asyncio
    async def test_repo_미주입_상태에서_수정_요청은_ValueError(self):
        uc, _ = _uc(with_catalog=False)
        with pytest.raises(ValueError):
            await uc.execute(
                "agent-1",
                UpdateAgentRequest(middleware_types=["model_retry"]),
                "req-1",
            )
