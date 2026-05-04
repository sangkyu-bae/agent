"""ForkAgentUseCase: 에이전트 포크 (전체 복사)."""
import uuid
from datetime import datetime, timezone

from src.application.agent_builder.schemas import ForkAgentResponse, WorkerInfo
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AccessCheckInput, ForkPolicy
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ForkAgentUseCase:
    def __init__(
        self,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._agent_repo = agent_repo
        self._logger = logger

    async def execute(
        self,
        source_agent_id: str,
        user_id: str,
        custom_name: str | None,
        viewer_department_ids: list[str],
        request_id: str,
    ) -> ForkAgentResponse:
        self._logger.info(
            "ForkAgentUseCase start",
            request_id=request_id,
            source_agent_id=source_agent_id,
            user_id=user_id,
        )
        try:
            source = await self._agent_repo.find_by_id(source_agent_id, request_id)
            if source is None:
                raise ValueError(f"에이전트를 찾을 수 없습니다: {source_agent_id}")

            ctx = AccessCheckInput(
                agent_owner_id=source.user_id,
                agent_visibility=source.visibility,
                agent_department_id=source.department_id,
                viewer_user_id=user_id,
                viewer_department_ids=viewer_department_ids,
                viewer_role="user",
            )
            if not ForkPolicy.can_fork(ctx):
                if source.user_id == user_id:
                    raise ValueError("자신의 에이전트는 포크할 수 없습니다")
                raise PermissionError("접근 권한이 없습니다")

            ForkPolicy.validate_source_status(source.status)

            now = datetime.now(timezone.utc)
            forked_name = custom_name or f"{source.name} (사본)"
            new_id = str(uuid.uuid4())

            forked = AgentDefinition(
                id=new_id,
                user_id=user_id,
                name=forked_name,
                description=source.description,
                system_prompt=source.system_prompt,
                flow_hint=source.flow_hint,
                workers=source.workers,
                llm_model_id=source.llm_model_id,
                status="active",
                visibility="private",
                department_id=None,
                temperature=source.temperature,
                forked_from=source_agent_id,
                forked_at=now,
                created_at=now,
                updated_at=now,
            )

            await self._agent_repo.save(forked, request_id)

            self._logger.info(
                "ForkAgentUseCase done",
                request_id=request_id,
                new_agent_id=new_id,
            )
            return ForkAgentResponse(
                agent_id=new_id,
                name=forked_name,
                forked_from=source_agent_id,
                forked_at=now.isoformat(),
                system_prompt=source.system_prompt,
                workers=[
                    WorkerInfo(
                        tool_id=w.tool_id,
                        worker_id=w.worker_id,
                        description=w.description,
                        sort_order=w.sort_order,
                        tool_config=w.tool_config,
                    )
                    for w in source.workers
                ],
                visibility="private",
                temperature=source.temperature,
                llm_model_id=source.llm_model_id,
            )
        except Exception as e:
            self._logger.error(
                "ForkAgentUseCase failed", exception=e, request_id=request_id
            )
            raise
