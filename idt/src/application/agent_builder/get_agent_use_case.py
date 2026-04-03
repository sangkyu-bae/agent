"""GetAgentUseCase: 에이전트 정의 조회."""
from src.application.agent_builder.schemas import GetAgentResponse, WorkerInfo
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class GetAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(self, agent_id: str, request_id: str) -> GetAgentResponse | None:
        self._logger.info(
            "GetAgentUseCase start", request_id=request_id, agent_id=agent_id
        )
        try:
            agent = await self._repository.find_by_id(agent_id, request_id)
            if agent is None:
                return None
            return GetAgentResponse(
                agent_id=agent.id,
                name=agent.name,
                description=agent.description,
                system_prompt=agent.system_prompt,
                tool_ids=[w.tool_id for w in agent.workers],
                workers=[
                    WorkerInfo(
                        tool_id=w.tool_id,
                        worker_id=w.worker_id,
                        description=w.description,
                        sort_order=w.sort_order,
                    )
                    for w in agent.workers
                ],
                flow_hint=agent.flow_hint,
                model_name=agent.model_name,
                status=agent.status,
                created_at=agent.created_at.isoformat(),
                updated_at=agent.updated_at.isoformat(),
            )
        except Exception as e:
            self._logger.error(
                "GetAgentUseCase failed", exception=e, request_id=request_id
            )
            raise
