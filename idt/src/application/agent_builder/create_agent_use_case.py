"""CreateAgentUseCase: 에이전트 생성 오케스트레이션."""
import uuid
from datetime import datetime, timezone

from src.application.agent_builder.document_template_binding import (
    build_document_template_plan,
    ensure_template_wiring,
    persist_document_template,
)
from src.application.agent_builder.prompt_generator import PromptGenerator
from src.application.agent_builder.schemas import (
    CreateAgentRequest, CreateAgentResponse, RagToolConfigRequest, WorkerInfo,
)
from src.domain.document_extractor.policies import DEFAULT_MAX_SLOTS
from src.application.agent_builder.sub_agent_worker_builder import SubAgentWorkerBuilder
from src.application.agent_builder.tool_selector import ToolSelector
from src.application.agent_skill.sync_agent_skills_use_case import (
    SyncAgentSkillsUseCase,
)
from src.domain.agent_builder.interfaces import (
    AgentDefinitionRepositoryInterface,
    SubscriptionRepositoryInterface,
)
from src.domain.agent_builder.policies import (
    AgentBuilderPolicy,
    VisibilityPolicy,
)
from src.domain.agent_builder.schemas import (
    AgentDefinition, ToolMeta, WorkerDefinition, WorkflowSkeleton,
)
from src.domain.agent_builder.tool_registry import get_tool_meta
from src.domain.collection.permission_interfaces import CollectionPermissionRepositoryInterface
from src.domain.department.interfaces import DepartmentRepositoryInterface
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
        dept_repo: DepartmentRepositoryInterface | None = None,
        skill_sync: "SyncAgentSkillsUseCase | None" = None,
        document_template_repo=None,
        source_archiver=None,
        max_template_slots: int = DEFAULT_MAX_SLOTS,
        mcp_server_repo=None,
    ) -> None:
        self._selector = tool_selector
        self._generator = prompt_generator
        self._repository = repository
        self._llm_model_repository = llm_model_repository
        self._perm_repo = perm_repo
        self._logger = logger
        self._subscription_repo = subscription_repo
        self._dept_repo = dept_repo
        self._skill_sync = skill_sync
        # document-template-extractor Design §3-4 (미주입 시 템플릿 요청은 에러)
        self._document_template_repo = document_template_repo
        self._source_archiver = source_archiver
        self._max_template_slots = max_template_slots
        # nl-agent-composer FR-08: mcp_* tool_id 메타 해석용 (미주입 시 mcp_* 거부)
        self._mcp_server_repo = mcp_server_repo
        self._sub_agent_builder = SubAgentWorkerBuilder(repository, logger)

    async def execute(
        self,
        request: CreateAgentRequest,
        request_id: str,
        viewer_role: str = "user",
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
                skeleton = await self._build_skeleton_from_tool_ids(
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
                parent_dept_ids = await self._resolve_department_ids(
                    request.user_id, request_id
                )
                sub_agent_workers = await self._sub_agent_builder.build(
                    configs=request.sub_agent_configs,
                    parent_user_id=request.user_id,
                    parent_department_ids=parent_dept_ids,
                    existing_tool_count=len(skeleton.workers),
                    request_id=request_id,
                )

            all_workers = list(skeleton.workers) + sub_agent_workers

            # Step 1.75 (document-template-extractor GA4): 확정 템플릿 검증 +
            # 대상 워커 tool_config 주입. 실패 시 예외 전파 = 생성 전체 롤백(R6).
            template_plan = None
            if request.document_template is not None:
                ensure_template_wiring(
                    self._document_template_repo, self._source_archiver
                )
                template_plan = build_document_template_plan(
                    request.document_template,
                    skeleton.workers,
                    self._max_template_slots,
                )

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

            # Step 3: 시스템 프롬프트 — 프리필 우선(nl-agent-composer D1), 없으면 자동 생성
            if request.system_prompt:
                system_prompt = request.system_prompt
            else:
                tool_metas = [
                    self._resolve_prompt_tool_meta(w) for w in skeleton.workers
                ]
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

            # Step 4.5: 등록 시점 부착 스킬 동기화 (agent-skill-toggle)
            # 무효 스킬 시 예외 전파 → 요청 트랜잭션 롤백(all-or-nothing).
            if request.skill_ids and self._skill_sync is not None:
                await self._skill_sync.sync(
                    saved.id, request.skill_ids, request_id,
                    viewer_user_id=request.user_id, viewer_role=viewer_role,
                )

            # Step 4.6 (document-template-extractor GA4): 원본 승격(D3) +
            # document_template 저장 — 동일 세션 트랜잭션 편승(R6).
            if template_plan is not None:
                await persist_document_template(
                    template_plan, saved.id,
                    self._document_template_repo, self._source_archiver,
                    request_id,
                )

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

    async def _build_skeleton_from_tool_ids(
        self,
        tool_ids: list[str],
        tool_configs: dict[str, RagToolConfigRequest] | None,
        request_id: str,
    ) -> WorkflowSkeleton:
        """사용자가 화면에서 직접 선택한 도구로 스켈레톤을 구성한다.

        tool_configs가 함께 오면 normalize한 tool_id로 매칭하여 해당 워커에 설정을 주입한다.
        mcp_* tool_id는 MCP 레지스트리에서 메타를 해석한다(nl-agent-composer FR-08).
        """
        configs_by_id = {
            self._normalize_tool_id(k): v
            for k, v in (tool_configs or {}).items()
        }
        workers: list[WorkerDefinition] = []
        seen: set[str] = set()
        for raw_id in tool_ids:
            tool_id = self._normalize_tool_id(raw_id)
            # 동일 서버의 카탈로그 도구 여러 개 → mcp_{srv} 워커 1개로 병합 (D5)
            if tool_id in seen:
                continue
            seen.add(tool_id)
            i = len(workers)
            if tool_id.startswith("mcp_"):
                description = await self._resolve_mcp_description(
                    tool_id, request_id
                )
            else:
                description = get_tool_meta(tool_id).description
            config = configs_by_id.get(tool_id)
            workers.append(WorkerDefinition(
                tool_id=tool_id,
                worker_id=f"{tool_id}_worker",
                description=description,
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

    async def _resolve_mcp_description(
        self, tool_id: str, request_id: str
    ) -> str:
        """mcp_{server_id} tool_id의 워커 설명을 MCP 레지스트리에서 해석한다."""
        if self._mcp_server_repo is None:
            raise ValueError(f"Unknown tool_id: {tool_id!r}")
        server_id = tool_id.removeprefix("mcp_")
        reg = await self._mcp_server_repo.find_by_id(server_id, request_id)
        if reg is None or not reg.is_active:
            raise ValueError(
                f"등록되지 않았거나 비활성화된 MCP 도구입니다: {tool_id}"
            )
        return reg.description or reg.name

    @staticmethod
    def _resolve_prompt_tool_meta(worker: WorkerDefinition) -> ToolMeta:
        """프롬프트 생성용 ToolMeta. mcp_* 워커는 레지스트리에 없으므로 워커 정보로 구성."""
        if worker.tool_id.startswith("mcp_"):
            return ToolMeta(
                tool_id=worker.tool_id,
                name=worker.tool_id,
                description=worker.description,
            )
        return get_tool_meta(worker.tool_id)

    @staticmethod
    def _normalize_tool_id(raw_key: str) -> str:
        """카탈로그 형식(`internal:{id}`, `mcp:{srv}:{tool}`)을 저장 형식으로 정규화.

        compose-tool-instructions D5: MCP 카탈로그 ID는 도구명이 아니라
        서버 단위 저장 형식 `mcp_{server_id}`로 매핑한다.
        """
        if raw_key.startswith("mcp:"):
            parts = raw_key.split(":")
            return f"mcp_{parts[1]}" if len(parts) >= 3 and parts[1] else raw_key
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

    async def _resolve_department_ids(
        self, user_id: str, request_id: str
    ) -> list[str]:
        """서브에이전트 가시성 검증용 부서 ID 목록. dept_repo 미주입 시 빈 목록."""
        if self._dept_repo is None:
            return []
        try:
            memberships = await self._dept_repo.find_departments_by_user(
                int(user_id), request_id
            )
        except (TypeError, ValueError):
            return []
        return [m.department_id for m in memberships]

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
