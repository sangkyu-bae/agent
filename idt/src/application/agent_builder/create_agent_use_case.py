"""CreateAgentUseCase: 에이전트 생성 오케스트레이션."""
import uuid
from datetime import datetime, timezone

from src.application.agent_builder.prompt_generator import PromptGenerator
from src.application.agent_builder.schemas import (
    CreateAgentRequest, CreateAgentResponse, RagToolConfigRequest, SubAgentConfigRequest, WorkerInfo,
)
from src.application.agent_builder.tool_selector import ToolSelector
from src.domain.agent_builder.interfaces import (
    AgentDefinitionRepositoryInterface,
    SubscriptionRepositoryInterface,
)
from src.domain.agent_builder.policies import (
    AgentBuilderPolicy,
    NestingDepthPolicy,
    SubAgentAccessPolicy,
    VisibilityPolicy,
)
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition, WorkflowSkeleton
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
        subscription_repo: SubscriptionRepositoryInterface | None = None,
    ) -> None:
        self._selector = tool_selector
        self._generator = prompt_generator
        self._repository = repository
        self._llm_model_repository = llm_model_repository
        self._perm_repo = perm_repo
        self._logger = logger
        self._subscription_repo = subscription_repo

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
            # 우선순위: 명시적 tool_ids → tool_configs → AI 자동 선택
            if request.tool_ids:
                skeleton = self._build_skeleton_from_tool_ids(
                    request.tool_ids, request.tool_configs, request_id
                )
            elif request.tool_configs:
                skeleton = self._build_skeleton_from_configs(
                    request.tool_configs, request_id
                )
            else:
                skeleton = await self._selector.select(
                    request.user_request, request_id
                )

            # Step 1.5: 서브 에이전트 워커 빌드
            sub_agent_workers: list[WorkerDefinition] = []
            if request.sub_agent_configs:
                sub_agent_workers = await self._build_sub_agent_workers(
                    configs=request.sub_agent_configs,
                    user_id=request.user_id,
                    request_id=request_id,
                    existing_tool_count=len(skeleton.workers),
                )

            all_workers = list(skeleton.workers) + sub_agent_workers

            # Step 2: Policy 검증
            if sub_agent_workers:
                AgentBuilderPolicy.validate_worker_count(all_workers)
            else:
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
                workers=all_workers,
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
                tool_ids=[w.tool_id for w in saved.workers if w.worker_type == "tool"],
                workers=[
                    WorkerInfo(
                        tool_id=w.tool_id,
                        worker_id=w.worker_id,
                        description=w.description,
                        sort_order=w.sort_order,
                        tool_config=w.tool_config,
                        worker_type=w.worker_type,
                        ref_agent_id=w.ref_agent_id,
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
                has_sub_agents=any(w.worker_type == "sub_agent" for w in saved.workers),
            )
        except Exception as e:
            self._logger.error(
                "CreateAgentUseCase failed", exception=e, request_id=request_id
            )
            raise

    def _build_skeleton_from_configs(
        self,
        tool_configs: dict[str, RagToolConfigRequest],
        request_id: str,
    ) -> WorkflowSkeleton:
        workers: list[WorkerDefinition] = []
        for i, (raw_key, config) in enumerate(tool_configs.items()):
            tool_id = self._normalize_tool_id(raw_key)
            meta = get_tool_meta(tool_id)
            workers.append(WorkerDefinition(
                tool_id=tool_id,
                worker_id=f"{tool_id}_worker",
                description=meta.description,
                sort_order=i,
                tool_config=config.model_dump(),
            ))
        flow_hint = " → ".join(w.tool_id for w in workers)
        self._logger.info(
            "Built skeleton from tool_configs",
            request_id=request_id,
            tool_ids=[w.tool_id for w in workers],
        )
        return WorkflowSkeleton(workers=workers, flow_hint=flow_hint)

    def _build_skeleton_from_tool_ids(
        self,
        tool_ids: list[str],
        tool_configs: dict[str, RagToolConfigRequest] | None,
        request_id: str,
    ) -> WorkflowSkeleton:
        """사용자가 화면에서 직접 선택한 도구로 스켈레톤을 구성한다.

        tool_configs가 함께 오면 normalize한 tool_id로 매칭하여 해당 워커에 설정을 주입한다.
        """
        configs_by_id = {
            self._normalize_tool_id(k): v
            for k, v in (tool_configs or {}).items()
        }
        workers: list[WorkerDefinition] = []
        for i, raw_id in enumerate(tool_ids):
            tool_id = self._normalize_tool_id(raw_id)
            meta = get_tool_meta(tool_id)
            config = configs_by_id.get(tool_id)
            workers.append(WorkerDefinition(
                tool_id=tool_id,
                worker_id=f"{tool_id}_worker",
                description=meta.description,
                sort_order=i,
                tool_config=config.model_dump() if config else None,
            ))
        flow_hint = " → ".join(w.tool_id for w in workers)
        self._logger.info(
            "Built skeleton from tool_ids",
            request_id=request_id,
            tool_ids=[w.tool_id for w in workers],
        )
        return WorkflowSkeleton(workers=workers, flow_hint=flow_hint)

    @staticmethod
    def _normalize_tool_id(raw_key: str) -> str:
        return raw_key.split(":")[-1] if ":" in raw_key else raw_key

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

    async def _build_sub_agent_workers(
        self,
        configs: list[SubAgentConfigRequest],
        user_id: str,
        request_id: str,
        existing_tool_count: int,
    ) -> list[WorkerDefinition]:
        workers: list[WorkerDefinition] = []

        for i, config in enumerate(configs):
            sub_agent = await self._repository.find_by_id(
                config.ref_agent_id, request_id
            )
            if sub_agent is None or sub_agent.status == "deleted":
                raise ValueError(
                    f"서브 에이전트를 찾을 수 없습니다: {config.ref_agent_id}"
                )

            is_subscribed = await self._check_subscription(
                user_id, config.ref_agent_id, request_id
            )
            if not SubAgentAccessPolicy.can_use_as_sub_agent(
                parent_owner_id=user_id,
                sub_agent_owner_id=sub_agent.user_id,
                is_subscribed=is_subscribed,
            ):
                raise PermissionError(
                    f"서브 에이전트 '{sub_agent.name}'에 대한 사용 권한이 없습니다"
                )

            description = config.description or sub_agent.description
            workers.append(WorkerDefinition(
                tool_id=f"sub_agent_{config.ref_agent_id[:8]}",
                worker_id=f"sub_agent_{sub_agent.name}_{i}",
                description=description,
                sort_order=existing_tool_count + i,
                worker_type="sub_agent",
                ref_agent_id=config.ref_agent_id,
            ))

        return workers

    async def _check_subscription(
        self, user_id: str, agent_id: str, request_id: str
    ) -> bool:
        if self._subscription_repo is None:
            return False
        sub = await self._subscription_repo.find_by_user_and_agent(
            user_id, agent_id, request_id
        )
        return sub is not None

    async def _resolve_llm_model_id(
        self, llm_model_id: str | None, request_id: str
    ) -> str:
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
