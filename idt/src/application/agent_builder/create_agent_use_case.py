"""CreateAgentUseCase: 에이전트 생성 오케스트레이션."""
import uuid
from datetime import datetime, timezone

from src.application.agent_builder.prompt_generator import PromptGenerator
from src.application.agent_builder.schemas import CreateAgentRequest, CreateAgentResponse, WorkerInfo
from src.application.agent_builder.tool_selector import ToolSelector
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AgentBuilderPolicy, VisibilityPolicy
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.agent_builder.tool_registry import get_tool_meta
from src.domain.collection.permission_interfaces import CollectionPermissionRepositoryInterface
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CreateAgentUseCase:
    def __init__(
        self,
        tool_selector: ToolSelector,
        prompt_generator: PromptGenerator,
        repository: AgentDefinitionRepositoryInterface,
        llm_model_repository: LlmModelRepositoryInterface,
        perm_repo: CollectionPermissionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._selector = tool_selector
        self._generator = prompt_generator
        self._repository = repository
        self._llm_model_repository = llm_model_repository
        self._perm_repo = perm_repo
        self._logger = logger

    async def execute(
        self, request: CreateAgentRequest, request_id: str
    ) -> CreateAgentResponse:
        self._logger.info(
            "CreateAgentUseCase start", request_id=request_id, user_id=request.user_id
        )
        try:
            # Step 0: LLM 모델 ID 결정 (지정 없으면 기본 모델 사용)
            llm_model_id = await self._resolve_llm_model_id(
                request.llm_model_id, request_id
            )

            # Step 1: 도구 선택 + 플로우 결정
            skeleton = await self._selector.select(request.user_request, request_id)

            # Step 1.5: tool_configs 적용
            if request.tool_configs:
                for worker in skeleton.workers:
                    if worker.tool_id in request.tool_configs:
                        worker.tool_config = request.tool_configs[
                            worker.tool_id
                        ].model_dump()

            # Step 2: Policy 검증
            AgentBuilderPolicy.validate_tool_count(len(skeleton.workers))
            AgentBuilderPolicy.validate_name(request.name)

            # Step 2.5: 컬렉션 scope 기반 visibility 자동 조정
            visibility, clamped, max_vis = await self._resolve_visibility(
                request, skeleton.workers, request_id
            )

            # Step 3: 시스템 프롬프트 자동 생성
            tool_metas = [get_tool_meta(w.tool_id) for w in skeleton.workers]
            system_prompt = await self._generator.generate(
                request.user_request, skeleton, tool_metas, request_id
            )
            AgentBuilderPolicy.validate_system_prompt(system_prompt)

            # Step 4: AgentDefinition 저장
            now = datetime.now(timezone.utc)
            agent = AgentDefinition(
                id=str(uuid.uuid4()),
                user_id=request.user_id,
                name=request.name,
                description=request.user_request,
                system_prompt=system_prompt,
                flow_hint=skeleton.flow_hint,
                workers=skeleton.workers,
                llm_model_id=llm_model_id,
                status="active",
                visibility=visibility,
                department_id=request.department_id,
                temperature=request.temperature,
                created_at=now,
                updated_at=now,
            )
            saved = await self._repository.save(agent, request_id)

            self._logger.info(
                "CreateAgentUseCase done", request_id=request_id, agent_id=saved.id
            )
            return CreateAgentResponse(
                agent_id=saved.id,
                name=saved.name,
                system_prompt=saved.system_prompt,
                tool_ids=[w.tool_id for w in saved.workers],
                workers=[
                    WorkerInfo(
                        tool_id=w.tool_id,
                        worker_id=w.worker_id,
                        description=w.description,
                        sort_order=w.sort_order,
                        tool_config=w.tool_config,
                    )
                    for w in saved.workers
                ],
                flow_hint=saved.flow_hint,
                llm_model_id=saved.llm_model_id,
                visibility=saved.visibility,
                visibility_clamped=clamped,
                max_visibility=max_vis,
                department_id=saved.department_id,
                temperature=saved.temperature,
                created_at=saved.created_at.isoformat(),
            )
        except Exception as e:
            self._logger.error(
                "CreateAgentUseCase failed", exception=e, request_id=request_id
            )
            raise

    async def _resolve_visibility(
        self,
        request: CreateAgentRequest,
        workers: list[WorkerDefinition],
        request_id: str,
    ) -> tuple[str, bool, str | None]:
        collection_names = self._extract_collection_names(workers)
        if not collection_names:
            return request.visibility, False, None
        scopes = await self._lookup_collection_scopes(
            collection_names, request_id
        )
        clamped_vis = VisibilityPolicy.clamp_visibility(
            request.visibility, scopes
        )
        max_vis = VisibilityPolicy.max_visibility_for_scopes(scopes)
        was_clamped = clamped_vis != request.visibility
        return clamped_vis, was_clamped, max_vis

    @staticmethod
    def _extract_collection_names(
        workers: list[WorkerDefinition],
    ) -> list[str]:
        names: list[str] = []
        for w in workers:
            if w.tool_config and w.tool_config.get("collection_name"):
                names.append(w.tool_config["collection_name"])
        return names

    async def _lookup_collection_scopes(
        self,
        collection_names: list[str],
        request_id: str,
    ) -> list[str]:
        scopes: list[str] = []
        for name in collection_names:
            perm = await self._perm_repo.find_by_collection_name(
                name, request_id
            )
            scopes.append(perm.scope.value if perm else "PERSONAL")
        return scopes

    async def _resolve_llm_model_id(
        self, llm_model_id: str | None, request_id: str
    ) -> str:
        """요청에 model_id가 없으면 기본 모델 사용."""
        if llm_model_id:
            found = await self._llm_model_repository.find_by_id(
                llm_model_id, request_id
            )
            if found is None:
                raise ValueError(f"LLM 모델을 찾을 수 없습니다: {llm_model_id}")
            return found.id

        default = await self._llm_model_repository.find_default(request_id)
        if default is None:
            raise ValueError("기본 LLM 모델이 설정되지 않았습니다.")
        return default.id
