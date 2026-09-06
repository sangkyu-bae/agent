"""CreateAgentUseCase: 에이전트 생성 오케스트레이션."""
import uuid
from datetime import datetime, timezone

from src.application.agent_builder.document_generation_type_binding import (
    build_document_generation_type_plan,
    ensure_generation_type_wiring,
    persist_document_generation_type,
)
from src.application.agent_builder.document_template_binding import (
    build_document_template_plan,
    ensure_template_wiring,
    persist_document_template,
)
from src.application.agent_builder.presentation_generator_binding import (
    apply_presentation_generator_config,
)
from src.application.agent_builder.schemas import (
    CreateAgentRequest,
    CreateAgentResponse,
    WorkerInfo,
)
from src.application.agent_builder.sub_agent_worker_builder import SubAgentWorkerBuilder
from src.application.agent_builder.worker_skeleton_builder import (
    WorkerSkeletonBuilder,
)
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
    AgentDefinition,
    WorkerDefinition,
    WorkflowSkeleton,
)
from src.domain.auth.entities import UserRole
from src.domain.collection.permission_interfaces import (
    CollectionPermissionRepositoryInterface,
)
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.document_extractor.policies import DEFAULT_MAX_SLOTS
from src.domain.document_generator.policies import DEFAULT_MAX_SECTIONS
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.interfaces import KnowledgeBaseRepositoryInterface
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface


class CreateAgentUseCase:
    def __init__(
        self,
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
        document_generation_type_repo=None,
        max_generation_sections: int = DEFAULT_MAX_SECTIONS,
        mcp_server_repo=None,
        kb_repo: KnowledgeBaseRepositoryInterface | None = None,
        tool_catalog_repo: "ToolCatalogRepositoryInterface | None" = None,
        middleware_catalog_repo=None,
    ) -> None:
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
        # doc-generator §4-3 (미주입 시 문서 유형 요청은 에러)
        self._document_generation_type_repo = document_generation_type_repo
        self._max_generation_sections = max_generation_sections
        # nl-agent-composer FR-08: mcp_* tool_id 메타 해석용 (미주입 시 mcp_* 거부)
        self._mcp_server_repo = mcp_server_repo
        # kb-rag-filter D7: kb_id 검증·scope clamp용 (kb_id 지정 요청은 주입 필수)
        self._kb_repo = kb_repo
        # builtin-tools D5: 빌트인 주입용 (미주입 시 주입 생략 — 무회귀)
        self._tool_catalog_repo = tool_catalog_repo
        # builtin-middleware D5: 빌트인 미들웨어 스냅샷용 (미주입 시 생략 — 무회귀)
        self._middleware_catalog_repo = middleware_catalog_repo
        self._sub_agent_builder = SubAgentWorkerBuilder(repository, logger)
        # agent-update-tool-editing D §2.3: 워커 빌드 규칙은 update 경로와 공유한다
        self._skeleton_builder = WorkerSkeletonBuilder(
            logger=logger,
            mcp_server_repo=mcp_server_repo,
            tool_catalog_repo=tool_catalog_repo,
        )

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
            # 우선순위: 명시적 tool_ids → tool_configs → 도구 없음(순수 대화형)
            # agent-instruction-required: LLM 도구 자동선택 제거 — 도구 구성은
            # 사용자가 직접(또는 Fix 에이전트로) 결정한다. 미지정 시 워커 0개.
            if request.tool_ids:
                skeleton = await self._skeleton_builder.build_from_tool_ids(
                    request.tool_ids, request.tool_configs, request_id
                )
            elif request.tool_configs:
                skeleton = self._skeleton_builder.build_from_configs(
                    request.tool_configs, request_id
                )
            else:
                skeleton = WorkflowSkeleton(workers=[], flow_hint="")

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

            # Step 1.8 (doc-generator §4-3): 문서 유형 검증 + 워커 tool_config 주입.
            # 실패 시 예외 전파 = 생성 전체 롤백(R6).
            generation_type_plan = None
            if request.document_generation_type is not None:
                ensure_generation_type_wiring(self._document_generation_type_repo)
                generation_type_plan = build_document_generation_type_plan(
                    request.document_generation_type,
                    skeleton.workers,
                    self._max_generation_sections,
                )

            # Step 1.9 (golden-sample-blueprint D7): 발표자료 워커 tool_config 주입.
            if request.presentation_generator is not None:
                apply_presentation_generator_config(
                    request.presentation_generator, skeleton.workers
                )

            # Step 2: Policy 검증
            if sub_agent_workers:
                AgentBuilderPolicy.validate_worker_count(all_workers)
            else:
                AgentBuilderPolicy.validate_tool_count(len(skeleton.workers))
            AgentBuilderPolicy.validate_name(request.name)

            # Step 2.5: 컬렉션/지식베이스 scope 기반 visibility 자동 조정
            # (kb-rag-filter D1/D7: KB 검증 → clamp → 물리 컬렉션 고정)
            kbs = await self._resolve_kbs(
                skeleton.workers, request_id, request.user_id, viewer_role
            )
            visibility, clamped, max_vis = await self._resolve_visibility(
                request, skeleton.workers, request_id, kbs
            )
            self._canonicalize_kb_collections(skeleton.workers, kbs)

            # Step 2.7 (builtin-tools D5): 빌트인 도구 주입 — 정책 검증(사용자
            # 선택분) 이후이므로 상한(MAX_TOOLS)에서 제외된다(D6). 빌트인은
            # tool_config가 없어 visibility/KB 해석 대상이 아니며, flow_hint에도
            # 포함하지 않는다(보조 도구 — supervisor 워커 목록으로만 인지).
            builtin_workers = await self._skeleton_builder.build_builtin_workers(
                all_workers, request.exclude_builtin_tool_ids, request_id
            )
            all_workers = all_workers + builtin_workers

            # Step 2.8 (builtin-middleware D5): 빌트인 미들웨어 스냅샷 —
            # exclude는 폼 전용 필드(채팅 초안 경로는 미사용 = LLM 우회 불가).
            middleware_types = await self._build_builtin_middleware(
                request.exclude_builtin_middleware_types, request_id
            )

            # Step 3: 시스템 프롬프트 필수 (agent-instruction-required)
            # LLM 자동생성 제거 — 지침은 사용자 입력 또는 Fix 에이전트 초안 전담.
            AgentBuilderPolicy.validate_system_prompt(request.system_prompt or "")
            system_prompt = request.system_prompt

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
                max_iterations=request.max_iterations,
                created_at=now,
                updated_at=now,
                middleware_types=middleware_types,
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

            # Step 4.7 (doc-generator §4-3): document_generation_type 저장 —
            # 동일 세션 트랜잭션 편승(R6).
            if generation_type_plan is not None:
                await persist_document_generation_type(
                    generation_type_plan, saved.id,
                    self._document_generation_type_repo, request_id,
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
                max_iterations=saved.max_iterations,
                created_at=saved.created_at.isoformat(),
                has_sub_agents=any(w.worker_type == "sub_agent" for w in saved.workers),
            )
        except Exception as e:
            self._logger.error(
                "CreateAgentUseCase failed", exception=e, request_id=request_id
            )
            raise
    async def _build_builtin_middleware(
        self,
        exclude_types: list[str] | None,
        request_id: str,
    ) -> list[str]:
        """builtin-middleware D5: 빌트인(is_builtin AND is_active) 타입 스냅샷.

        카탈로그 sort_order 순서를 유지하고, 수동 opt-out(exclude)만 제외한다.
        config는 저장하지 않는다 — 설정값은 카탈로그 default_config 단일 소스.
        """
        if self._middleware_catalog_repo is None:
            return []
        entries = await self._middleware_catalog_repo.list_builtin(request_id)
        exclude = set(exclude_types or [])
        types = [
            e.middleware_type.value
            for e in sorted(entries, key=lambda e: e.sort_order)
            if e.middleware_type.value not in exclude
        ]
        if types:
            self._logger.info(
                "Builtin middleware snapshot",
                request_id=request_id,
                middleware_types=types,
            )
        return types
    async def _resolve_visibility(
        self,
        request: CreateAgentRequest,
        workers: list[WorkerDefinition],
        request_id: str,
        kbs: dict[str, KnowledgeBase] | None = None,
    ) -> tuple[str, bool, str | None]:
        collection_names = self._extract_collection_names(workers)
        kb_scopes = [kb.scope.value for kb in (kbs or {}).values()]
        if not collection_names and not kb_scopes:
            return request.visibility, False, None
        scopes = await self._lookup_collection_scopes(
            collection_names, request_id
        )
        scopes += kb_scopes
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
        """kb-rag-filter D7: kb_id 워커는 KB scope가 지배 — 컬렉션 조회 제외."""
        names: list[str] = []
        for w in workers:
            if not w.tool_config or w.tool_config.get("kb_id"):
                continue
            if w.tool_config.get("collection_name"):
                names.append(w.tool_config["collection_name"])
        return names

    async def _resolve_kbs(
        self,
        workers: list[WorkerDefinition],
        request_id: str,
        user_id: str,
        viewer_role: str,
    ) -> dict[str, KnowledgeBase]:
        """kb-rag-filter D3: kb_id 수집 + 존재/읽기권한 검증.

        미존재 → ValueError(400), 읽기권한 없음 → PermissionError(403).
        """
        kb_ids = {
            w.tool_config["kb_id"]
            for w in workers
            if w.tool_config and w.tool_config.get("kb_id")
        }
        if not kb_ids:
            return {}
        if self._kb_repo is None:
            raise ValueError(
                "kb_id가 지정된 도구 설정에는 kb_repo 주입이 필요합니다"
            )
        role = (
            UserRole.ADMIN
            if viewer_role == UserRole.ADMIN.value
            else UserRole.USER
        )
        dept_ids = (
            []
            if role == UserRole.ADMIN
            else await self._resolve_department_ids(user_id, request_id)
        )
        kbs: dict[str, KnowledgeBase] = {}
        for kb_id in kb_ids:
            kb = await self._kb_repo.find_by_id(kb_id, request_id)
            if kb is None:
                raise ValueError(f"Knowledge base not found: {kb_id}")
            if not KnowledgeBasePolicy.can_read_ref(
                self._owner_ref(user_id), role, kb, dept_ids
            ):
                raise PermissionError(
                    f"No read access to knowledge base '{kb_id}'"
                )
            kbs[kb_id] = kb
        return kbs

    @staticmethod
    def _owner_ref(user_id: str | None) -> int | None:
        """user_id(str) → KB owner_id(int) 비교용. 비정수 형식은 소유자 불일치."""
        try:
            return int(user_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _canonicalize_kb_collections(
        workers: list[WorkerDefinition],
        kbs: dict[str, KnowledgeBase],
    ) -> None:
        """kb-rag-filter D1: kb_id 워커의 collection_name을 KB 물리 컬렉션으로 고정."""
        for w in workers:
            kb_id = w.tool_config.get("kb_id") if w.tool_config else None
            if kb_id:
                w.tool_config["collection_name"] = kbs[kb_id].collection_name

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
