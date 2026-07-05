"""포크 시 스케줄 미복사 회귀 테스트 (agent-schedule R5).

스케줄은 agent_schedule 별도 테이블(agent_id FK)에만 존재하고, 포크 두 경로
(ForkAgentUseCase / AutoForkService)는 AgentDefinition 필드를 화이트리스트로
복사하므로 사본에는 스케줄이 따라가지 않는다. 이 테스트는 그 구조적 보장을
고정한다 — 포크 로직이 스케줄 저장소를 알게 되거나(생성자 시그니처 변화),
사본이 원본 id 를 재사용하게 되면 실패한다.
"""
import inspect
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.auto_fork_service import AutoForkService
from src.application.agent_builder.fork_agent_use_case import ForkAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition

NOW = datetime.now(timezone.utc)
SOURCE_AGENT_ID = "src-agent"


def _source_agent(visibility="public") -> AgentDefinition:
    return AgentDefinition(
        id=SOURCE_AGENT_ID, user_id="owner-1", name="원본",
        description="설명", system_prompt="프롬프트", flow_hint=None,
        workers=[WorkerDefinition(tool_id="t", worker_id="w", description="d")],
        llm_model_id="m", status="active",
        visibility=visibility, temperature=0.7,
        created_at=NOW, updated_at=NOW,
    )


# 스케줄 저장소 시뮬레이션: agent_id 로 조회하는 별도 테이블 구조
SCHEDULE_STORE: dict[str, list[str]] = {SOURCE_AGENT_ID: ["sched-1", "sched-2"]}


class TestForkAgentUseCaseExcludesSchedules:
    @pytest.mark.asyncio
    async def test_forked_agent_has_no_schedules(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_source_agent())
        repo.save = AsyncMock()
        uc = ForkAgentUseCase(agent_repo=repo, logger=MagicMock())

        result = await uc.execute(
            SOURCE_AGENT_ID, "viewer-1", None, [], "req-1"
        )

        forked: AgentDefinition = repo.save.call_args[0][0]
        assert forked.id != SOURCE_AGENT_ID  # 새 id → FK 기반 스케줄 미승계
        assert SCHEDULE_STORE.get(forked.id) is None
        assert SCHEDULE_STORE[SOURCE_AGENT_ID] == ["sched-1", "sched-2"]  # 원본 보존
        assert result.forked_from == SOURCE_AGENT_ID

    def test_fork_use_case_has_no_schedule_dependency(self):
        """포크가 스케줄 저장소를 주입받기 시작하면(=복사 시도 가능성) 실패."""
        params = inspect.signature(ForkAgentUseCase.__init__).parameters
        assert not any("schedule" in name for name in params)


class TestAutoForkServiceExcludesSchedules:
    @pytest.mark.asyncio
    async def test_auto_forked_agents_have_no_schedules(self):
        agent_repo = MagicMock()
        agent_repo.list_by_user = AsyncMock(return_value=[])
        agent_repo.save = AsyncMock()
        subscription_repo = MagicMock()
        subscriber = MagicMock()
        subscriber.user_id = "sub-1"
        subscription_repo.find_subscribers_by_agent = AsyncMock(
            return_value=[subscriber]
        )
        subscription_repo.delete_by_agent = AsyncMock()
        service = AutoForkService(
            agent_repo=agent_repo,
            subscription_repo=subscription_repo,
            logger=MagicMock(),
        )

        count = await service.fork_for_subscribers(_source_agent(), "req-1")

        assert count == 1
        forked: AgentDefinition = agent_repo.save.call_args[0][0]
        assert forked.id != SOURCE_AGENT_ID
        assert SCHEDULE_STORE.get(forked.id) is None

    def test_auto_fork_service_has_no_schedule_dependency(self):
        params = inspect.signature(AutoForkService.__init__).parameters
        assert not any("schedule" in name for name in params)
