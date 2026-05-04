"""AutoForkService: 원본 에이전트 삭제 시 구독자를 위한 자동 포크."""
import uuid
from datetime import datetime, timezone

from src.domain.agent_builder.interfaces import (
    AgentDefinitionRepositoryInterface,
    SubscriptionRepositoryInterface,
)
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class AutoForkService:
    """원본 에이전트 삭제/비공개 시 구독자를 위한 자동 포크 서비스."""

    def __init__(
        self,
        agent_repo: AgentDefinitionRepositoryInterface,
        subscription_repo: SubscriptionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._agent_repo = agent_repo
        self._subscription_repo = subscription_repo
        self._logger = logger

    async def fork_for_subscribers(
        self, agent: AgentDefinition, request_id: str
    ) -> int:
        """삭제 직전, 구독자들에게 자동 포크 생성. 생성 건수 반환."""
        self._logger.info(
            "AutoForkService.fork_for_subscribers start",
            request_id=request_id,
            agent_id=agent.id,
        )
        try:
            subscribers = await self._subscription_repo.find_subscribers_by_agent(
                agent.id, request_id
            )
            if not subscribers:
                return 0

            fork_count = 0
            now = datetime.now(timezone.utc)

            for sub in subscribers:
                user_agents = await self._agent_repo.list_by_user(
                    sub.user_id, request_id
                )
                already_forked = any(
                    a.forked_from == agent.id for a in user_agents
                )
                if already_forked:
                    continue

                forked = AgentDefinition(
                    id=str(uuid.uuid4()),
                    user_id=sub.user_id,
                    name=f"{agent.name} (자동 보존)",
                    description=agent.description,
                    system_prompt=agent.system_prompt,
                    flow_hint=agent.flow_hint,
                    workers=agent.workers,
                    llm_model_id=agent.llm_model_id,
                    status="active",
                    visibility="private",
                    department_id=None,
                    temperature=agent.temperature,
                    forked_from=agent.id,
                    forked_at=now,
                    created_at=now,
                    updated_at=now,
                )
                await self._agent_repo.save(forked, request_id)
                fork_count += 1

            await self._subscription_repo.delete_by_agent(agent.id, request_id)

            self._logger.info(
                "AutoForkService.fork_for_subscribers done",
                request_id=request_id,
                fork_count=fork_count,
            )
            return fork_count
        except Exception as e:
            self._logger.error(
                "AutoForkService.fork_for_subscribers failed",
                exception=e,
                request_id=request_id,
            )
            raise
