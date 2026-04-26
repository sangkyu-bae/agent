"""UpdateAgentUseCase: 시스템 프롬프트 / 이름 수정."""
from src.application.agent_builder.schemas import UpdateAgentRequest, UpdateAgentResponse
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AccessCheckInput, UpdateAgentPolicy, VisibilityPolicy
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.collection.permission_interfaces import CollectionPermissionRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class UpdateAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        perm_repo: CollectionPermissionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._perm_repo = perm_repo
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        request: UpdateAgentRequest,
        request_id: str,
        viewer_user_id: str | None = None,
    ) -> UpdateAgentResponse:
        self._logger.info(
            "UpdateAgentUseCase start", request_id=request_id, agent_id=agent_id
        )
        try:
            agent = await self._repository.find_by_id(agent_id, request_id)
            if agent is None:
                raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")

            if viewer_user_id is not None:
                ctx = AccessCheckInput(
                    agent_owner_id=agent.user_id,
                    agent_visibility=agent.visibility,
                    agent_department_id=agent.department_id,
                    viewer_user_id=viewer_user_id,
                    viewer_department_ids=[],
                    viewer_role="user",
                )
                if not VisibilityPolicy.can_edit(ctx):
                    raise PermissionError("수정 권한이 없습니다")

            UpdateAgentPolicy.validate_update(
                status=agent.status, system_prompt=request.system_prompt
            )

            if request.visibility is not None:
                await self._validate_visibility_scope(
                    request.visibility, agent.workers, request_id
                )

            agent.apply_update(
                system_prompt=request.system_prompt,
                name=request.name,
                visibility=request.visibility,
                department_id=request.department_id,
                temperature=request.temperature,
            )
            updated = await self._repository.update(agent, request_id)

            self._logger.info(
                "UpdateAgentUseCase done", request_id=request_id, agent_id=agent_id
            )
            return UpdateAgentResponse(
                agent_id=updated.id,
                name=updated.name,
                system_prompt=updated.system_prompt,
                updated_at=updated.updated_at.isoformat(),
            )
        except Exception as e:
            self._logger.error(
                "UpdateAgentUseCase failed", exception=e, request_id=request_id
            )
            raise

    async def _validate_visibility_scope(
        self,
        requested: str,
        workers: list[WorkerDefinition],
        request_id: str,
    ) -> None:
        collection_names = [
            w.tool_config["collection_name"]
            for w in workers
            if w.tool_config and w.tool_config.get("collection_name")
        ]
        if not collection_names:
            return
        scopes: list[str] = []
        for name in collection_names:
            perm = await self._perm_repo.find_by_collection_name(
                name, request_id
            )
            scopes.append(perm.scope.value if perm else "PERSONAL")
        clamped = VisibilityPolicy.clamp_visibility(requested, scopes)
        if clamped != requested:
            raise ValueError(
                f"컬렉션 scope 제한으로 visibility를 "
                f"'{requested}'로 설정할 수 없습니다. "
                f"최대 허용: '{clamped}'"
            )
