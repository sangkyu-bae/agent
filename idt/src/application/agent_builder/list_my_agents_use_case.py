"""ListMyAgentsUseCase: 내 에이전트 통합 목록 (소유+구독+포크)."""
from src.application.agent_builder.schemas import (
    ListMyAgentsResponse,
    MyAgentSummary,
)
from src.domain.agent_builder.interfaces import (
    AgentDefinitionRepositoryInterface,
    SubscriptionRepositoryInterface,
)
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListMyAgentsUseCase:
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
        self,
        user_id: str,
        filter_type: str,
        search: str | None,
        page: int,
        size: int,
        request_id: str,
    ) -> ListMyAgentsResponse:
        self._logger.info(
            "ListMyAgentsUseCase start",
            request_id=request_id,
            user_id=user_id,
            filter=filter_type,
        )
        try:
            all_items: list[MyAgentSummary] = []

            if filter_type in ("all", "owned", "forked"):
                user_agents = await self._agent_repo.list_by_user(user_id, request_id)
                for agent in user_agents:
                    if agent.status == "deleted":
                        continue
                    is_forked = agent.forked_from is not None
                    if filter_type == "owned" and is_forked:
                        continue
                    if filter_type == "forked" and not is_forked:
                        continue
                    source_type = "forked" if is_forked else "owned"
                    all_items.append(self._to_summary(agent, source_type))

            if filter_type in ("all", "subscribed"):
                subscriptions = await self._subscription_repo.list_by_user(
                    user_id, request_id
                )
                for sub in subscriptions:
                    agent = await self._agent_repo.find_by_id(
                        sub.agent_id, request_id
                    )
                    if agent is None or agent.status == "deleted":
                        continue
                    summary = self._to_summary(agent, "subscribed")
                    summary.is_pinned = sub.is_pinned
                    all_items.append(summary)

            if search:
                keyword = search.lower()
                all_items = [
                    item
                    for item in all_items
                    if keyword in item.name.lower()
                    or keyword in item.description.lower()
                ]

            all_items.sort(key=lambda x: x.created_at, reverse=True)
            total = len(all_items)
            offset = (page - 1) * size
            paged = all_items[offset : offset + size]

            self._logger.info(
                "ListMyAgentsUseCase done",
                request_id=request_id,
                total=total,
            )
            return ListMyAgentsResponse(
                agents=paged,
                total=total,
                page=page,
                size=size,
            )
        except Exception as e:
            self._logger.error(
                "ListMyAgentsUseCase failed", exception=e, request_id=request_id
            )
            raise

    def _to_summary(
        self, agent: AgentDefinition, source_type: str
    ) -> MyAgentSummary:
        return MyAgentSummary(
            agent_id=agent.id,
            name=agent.name,
            description=agent.description,
            source_type=source_type,
            visibility=agent.visibility,
            temperature=agent.temperature,
            owner_user_id=agent.user_id,
            forked_from=agent.forked_from,
            is_pinned=False,
            created_at=agent.created_at.isoformat(),
        )
