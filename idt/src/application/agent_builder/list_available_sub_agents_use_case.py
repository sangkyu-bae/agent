"""ListAvailableSubAgentsUseCase: 서브 에이전트로 사용 가능한 에이전트 목록."""
from src.application.agent_builder.schemas import (
    AvailableSubAgentsResponse,
    SubAgentCandidate,
)
from src.domain.agent_builder.interfaces import (
    AgentDefinitionRepositoryInterface,
    SubscriptionRepositoryInterface,
)
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListAvailableSubAgentsUseCase:
    def __init__(
        self,
        agent_repo: AgentDefinitionRepositoryInterface,
        subscription_repo: SubscriptionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._agent_repo = agent_repo
        self._subscription_repo = subscription_repo
        self._logger = logger

    async def execute(
        self, user_id: str, request_id: str
    ) -> AvailableSubAgentsResponse:
        self._logger.info(
            "ListAvailableSubAgentsUseCase start",
            request_id=request_id,
            user_id=user_id,
        )
        try:
            candidates: list[SubAgentCandidate] = []

            owned = await self._agent_repo.list_by_user(user_id, request_id)
            for agent in owned:
                if agent.status == "deleted":
                    continue
                candidates.append(self._to_candidate(agent, "owned"))

            subscriptions = await self._subscription_repo.list_by_user(
                user_id, request_id
            )
            for sub in subscriptions:
                agent = await self._agent_repo.find_by_id(
                    sub.agent_id, request_id
                )
                if agent is None or agent.status == "deleted":
                    continue
                candidates.append(self._to_candidate(agent, "subscribed"))

            self._logger.info(
                "ListAvailableSubAgentsUseCase done",
                request_id=request_id,
                count=len(candidates),
            )
            return AvailableSubAgentsResponse(agents=candidates)
        except Exception as e:
            self._logger.error(
                "ListAvailableSubAgentsUseCase failed",
                exception=e,
                request_id=request_id,
            )
            raise

    @staticmethod
    def _to_candidate(
        agent: AgentDefinition, source_type: str
    ) -> SubAgentCandidate:
        return SubAgentCandidate(
            agent_id=agent.id,
            name=agent.name,
            description=agent.description,
            source_type=source_type,
            tool_ids=[
                w.tool_id for w in agent.workers if w.worker_type == "tool"
            ],
            has_sub_agents=any(
                w.worker_type == "sub_agent" for w in agent.workers
            ),
        )
