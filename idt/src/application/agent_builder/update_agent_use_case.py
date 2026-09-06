"""UpdateAgentUseCase: 시스템 프롬프트 / 이름 / 도구 / 서브에이전트 / 문서 수정."""
from dataclasses import dataclass

from src.application.agent_builder.document_generation_type_binding import (
    DOCUMENT_GENERATOR_TOOL_ID,
    build_document_generation_type_plan,
    ensure_generation_type_wiring,
    persist_document_generation_type,
)
from src.application.agent_builder.document_template_binding import (
    DOCUMENT_EXTRACTOR_TOOL_ID,
    build_document_template_plan,
    ensure_template_wiring,
    persist_document_template,
)
from src.application.agent_builder.presentation_generator_binding import (
    apply_presentation_generator_config,
)
from src.application.agent_builder.schemas import (
    UpdateAgentRequest,
    UpdateAgentResponse,
)
from src.application.agent_builder.sub_agent_worker_builder import SubAgentWorkerBuilder
from src.application.agent_builder.worker_skeleton_builder import (
    WorkerSkeletonBuilder,
    make_worker_id,
)
from src.application.agent_skill.sync_agent_skills_use_case import (
    SyncAgentSkillsUseCase,
)
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import (
    AccessCheckInput,
    AgentBuilderPolicy,
    UpdateAgentPolicy,
    VisibilityPolicy,
)
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.auth.entities import UserRole
from src.domain.collection.permission_interfaces import (
    CollectionPermissionRepositoryInterface,
)
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.document_extractor.policies import DEFAULT_MAX_SLOTS
from src.domain.document_generator.policies import DEFAULT_MAX_SECTIONS
from src.domain.knowledge_base.interfaces import KnowledgeBaseRepositoryInterface
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


@dataclass(frozen=True)
class _ClampResult:
    """도구 변경으로 발생한 visibility 조정 결과 (응답 통지용)."""

    clamped: bool = False
    max_visibility: str | None = None


_NO_CLAMP = _ClampResult()


class UpdateAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        perm_repo: CollectionPermissionRepositoryInterface,
        logger: LoggerInterface,
        dept_repo: DepartmentRepositoryInterface | None = None,
        skill_sync: "SyncAgentSkillsUseCase | None" = None,
        document_template_repo=None,
        source_archiver=None,
        max_template_slots: int = DEFAULT_MAX_SLOTS,
        document_generation_type_repo=None,
        max_generation_sections: int = DEFAULT_MAX_SECTIONS,
        kb_repo: KnowledgeBaseRepositoryInterface | None = None,
        llm_model_repo: LlmModelRepositoryInterface | None = None,
        middleware_catalog_repo=None,
        tool_catalog_repo=None,
        mcp_server_repo=None,
    ) -> None:
        self._repository = repository
        self._perm_repo = perm_repo
        # kb-rag-filter D7: kb_id 워커 scope 검증용 (kb_id 워커 존재 시 주입 필수)
        self._kb_repo = kb_repo
        self._logger = logger
        self._dept_repo = dept_repo
        self._skill_sync = skill_sync
        # document-template-extractor Design §3-4 (미주입 시 템플릿 요청은 에러)
        self._document_template_repo = document_template_repo
        self._source_archiver = source_archiver
        self._max_template_slots = max_template_slots
        # doc-generator §4-3 (미주입 시 문서 유형 요청은 에러)
        self._document_generation_type_repo = document_generation_type_repo
        self._max_generation_sections = max_generation_sections
        # agent-builder-edit-mapping FR-5: llm_model_id 수정 시 존재 검증용
        self._llm_model_repo = llm_model_repo
        # builtin-middleware D5: middleware_types 수정 시 카탈로그 존재 검증용
        self._middleware_catalog_repo = middleware_catalog_repo
        self._sub_agent_builder = SubAgentWorkerBuilder(repository, logger)
        # agent-update-tool-editing D §2.3: 워커 빌드 규칙은 create 와 공유한다
        # (미주입 시 빌트인 주입 생략 / mcp_* 는 ValueError → 422).
        self._skeleton_builder = WorkerSkeletonBuilder(
            logger=logger,
            mcp_server_repo=mcp_server_repo,
            tool_catalog_repo=tool_catalog_repo,
        )

    async def execute(
        self,
        agent_id: str,
        request: UpdateAgentRequest,
        request_id: str,
        viewer_user_id: str | None = None,
        viewer_role: str = "user",
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

            # agent-update-tool-editing D §7: tool_ids 가 함께 오면 재구성된
            # 새 워커 기준으로 검증해야 하므로 호출 지점을 뒤로 미룬다.
            if request.visibility is not None and request.tool_ids is None:
                await self._validate_visibility_scope(
                    request.visibility, agent.workers, request_id,
                    viewer_user_id or agent.user_id, viewer_role,
                )

            # agent-builder-edit-mapping FR-5: None = 모델 변경 안 함
            if request.llm_model_id is not None:
                await self._validate_llm_model(request.llm_model_id, request_id)

            # builtin-middleware D5: None = 미변경, 값 = 전체 교체(검증+dedupe)
            middleware_types = None
            if request.middleware_types is not None:
                middleware_types = await self._validate_middleware_types(
                    request.middleware_types, request_id
                )

            agent.apply_update(
                system_prompt=request.system_prompt,
                name=request.name,
                visibility=request.visibility,
                department_id=request.department_id,
                temperature=request.temperature,
                max_iterations=request.max_iterations,
                llm_model_id=request.llm_model_id,
                middleware_types=middleware_types,
            )

            # 도구 구성 교체 (agent-update-tool-editing D §2.2):
            # 재구성 → 종속정리 → scope clamp → 정책검증 순서. 서브에이전트
            # 재배치·문서/발표자료 바인딩보다 **앞서야** 한다 (새 워커가 있어야
            # 바인딩이 주입할 대상을 찾는다 — 이 순서가 원 결함의 해소 지점).
            clamp = _NO_CLAMP
            if request.tool_ids is not None:
                clamp = await self._rebuild_tool_workers(
                    agent, request, request_id,
                    viewer_user_id or agent.user_id, viewer_role,
                )
            elif request.tool_configs is not None:
                raise ValueError(
                    "tool_configs 는 tool_ids 와 함께 전달해야 합니다."
                )

            if request.sub_agent_configs is not None:
                await self._apply_sub_agents(
                    agent=agent,
                    configs=request.sub_agent_configs,
                    viewer_user_id=viewer_user_id,
                    request_id=request_id,
                )

            # 부착 스킬 동기화 (agent-skill-toggle): None = 변경 안 함.
            if request.skill_ids is not None and self._skill_sync is not None:
                await self._skill_sync.sync(
                    agent.id, request.skill_ids, request_id,
                    viewer_user_id=viewer_user_id or agent.user_id,
                    viewer_role=viewer_role,
                )

            # 문서 템플릿 교체 (document-template-extractor D4): None = 변경 안 함.
            # 기존 active soft-delete → 신규 저장 → worker tool_config 갱신
            # (repository.update의 _sync_workers가 영속).
            if request.document_template is not None:
                await self._replace_document_template(agent, request, request_id)

            # 문서 유형 교체 (doc-generator §4-3): None = 변경 안 함.
            # 기존 active soft-delete → 신규 저장 → worker tool_config 갱신.
            if request.document_generation_type is not None:
                await self._replace_document_generation_type(
                    agent, request, request_id
                )

            # 발표자료 설정 교체 (golden-sample-blueprint D7): None = 변경 안 함.
            if request.presentation_generator is not None:
                apply_presentation_generator_config(
                    request.presentation_generator, agent.workers
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
                visibility=updated.visibility,
                visibility_clamped=clamp.clamped,
                max_visibility=clamp.max_visibility,
            )
        except Exception as e:
            self._logger.error(
                "UpdateAgentUseCase failed", exception=e, request_id=request_id
            )
            raise

    async def _rebuild_tool_workers(
        self,
        agent,
        request: UpdateAgentRequest,
        request_id: str,
        user_id: str,
        viewer_role: str,
    ) -> _ClampResult:
        """도구 워커를 목표 상태로 재구성한다 (D §2.2 ①~⑤).

        Raises:
            ValueError: 미지 도구·비활성 MCP·정책 위반 (요청 422/409)
            PermissionError: KB 읽기권한 없음 (403)
        """
        previous = {
            w.tool_id: w for w in agent.workers if w.worker_type == "tool"
        }
        skeleton = await self._skeleton_builder.build_from_tool_ids(
            request.tool_ids, request.tool_configs, request_id
        )
        self._inherit_tool_configs(skeleton.workers, previous)

        # 정책은 사용자 선택분 기준 (빌트인은 상한에서 제외 — builtin-tools D6)
        subs = [w for w in agent.workers if w.worker_type == "sub_agent"]
        if subs:
            AgentBuilderPolicy.validate_worker_count(skeleton.workers + subs)
        else:
            AgentBuilderPolicy.validate_tool_count(len(skeleton.workers))

        builtin_workers = await self._skeleton_builder.build_builtin_workers(
            skeleton.workers, None, request_id
        )
        tool_workers = skeleton.workers + builtin_workers

        # kb-rag-filter D1/D3/D7: 존재·권한 검증 → 물리 컬렉션 고정 → clamp
        kbs = await self._resolve_kbs(
            tool_workers, request_id, user_id, viewer_role
        )
        self._canonicalize_kb_collections(tool_workers, kbs)

        agent.replace_tool_workers(tool_workers)
        agent.flow_hint = skeleton.flow_hint

        removed = set(previous) - {w.tool_id for w in tool_workers}
        await self._cleanup_removed_tool_deps(agent, removed, request_id)

        self._logger.info(
            "Agent tool workers rebuilt",
            request_id=request_id,
            agent_id=agent.id,
            added_tool_ids=[
                w.tool_id for w in tool_workers if w.tool_id not in previous
            ],
            removed_tool_ids=sorted(removed),
        )
        return await self._apply_scope_clamp(
            agent, request, tool_workers, kbs, request_id, user_id, viewer_role
        )

    @staticmethod
    def _inherit_tool_configs(
        workers: list[WorkerDefinition],
        previous: dict[str, WorkerDefinition],
    ) -> None:
        """FR-03: 유지 도구는 기존 tool_config 승계 (요청 전달분이 우선)."""
        for w in workers:
            if w.tool_config is None and w.tool_id in previous:
                w.tool_config = previous[w.tool_id].tool_config

    async def _apply_scope_clamp(
        self,
        agent,
        request: UpdateAgentRequest,
        workers: list[WorkerDefinition],
        kbs: dict,
        request_id: str,
        user_id: str,
        viewer_role: str,
    ) -> _ClampResult:
        """FR-06: 도구 변경 후 scope 재해석.

        명시적 visibility 요청은 위반 시 422 거부(기존 계약), 미요청 시에는
        현재 visibility 를 자동 clamp 하고 그 사실을 응답으로 알린다 (D §7).
        """
        if request.visibility is not None:
            await self._validate_visibility_scope(
                request.visibility, workers, request_id, user_id, viewer_role
            )
            return _NO_CLAMP

        scopes = await self._lookup_collection_scopes(workers, request_id)
        scopes += [kb.scope.value for kb in kbs.values()]
        if not scopes:
            return _NO_CLAMP

        clamped_vis = VisibilityPolicy.clamp_visibility(agent.visibility, scopes)
        max_vis = VisibilityPolicy.max_visibility_for_scopes(scopes)
        if clamped_vis == agent.visibility:
            return _ClampResult(clamped=False, max_visibility=max_vis)

        self._logger.info(
            "Agent visibility clamped by tool scope",
            request_id=request_id, agent_id=agent.id,
            before=agent.visibility, after=clamped_vis,
        )
        # department 로 낮아졌는데 소속 부서가 없으면 유효하지 않은 조합이므로
        # private 까지 내린다 (AgentDefinition 불변식과 정합).
        if clamped_vis == "department" and agent.department_id is None:
            clamped_vis = "private"
        agent.visibility = clamped_vis
        return _ClampResult(clamped=True, max_visibility=max_vis)

    async def _cleanup_removed_tool_deps(
        self, agent, removed_tool_ids: set[str], request_id: str
    ) -> None:
        """FR-04: 제거된 도구의 종속 레코드를 soft-delete (고아 방지)."""
        for tool_id, repo in (
            (DOCUMENT_EXTRACTOR_TOOL_ID, self._document_template_repo),
            (DOCUMENT_GENERATOR_TOOL_ID, self._document_generation_type_repo),
        ):
            if tool_id not in removed_tool_ids or repo is None:
                continue
            existing = await repo.find_active_by_agent_worker(
                agent.id, make_worker_id(tool_id), request_id
            )
            if existing is not None:
                await repo.soft_delete(existing.id, request_id)

    async def _validate_middleware_types(
        self, middleware_types: list[str], request_id: str
    ) -> list[str]:
        """카탈로그 존재 검증 + 순서 보존 dedupe (비활성은 허용 — 실행 병합이 방어).

        builtin-middleware D5: 미지 타입은 ValueError(400).
        """
        if self._middleware_catalog_repo is None:
            raise ValueError(
                "middleware_types 수정에는 middleware_catalog_repo 주입이 필요합니다"
            )
        catalog = await self._middleware_catalog_repo.list_all(request_id)
        known = {e.middleware_type.value for e in catalog}
        deduped: list[str] = []
        for t in middleware_types:
            if t not in known:
                raise ValueError(f"알 수 없는 미들웨어 타입입니다: {t}")
            if t not in deduped:
                deduped.append(t)
        return deduped

    async def _validate_llm_model(
        self, llm_model_id: str, request_id: str
    ) -> None:
        """모델 존재 검증 (CreateAgentUseCase._resolve_llm_model_id와 동일 규칙)."""
        if self._llm_model_repo is None:
            raise ValueError("llm_model_id 수정에는 llm_model_repo 주입이 필요합니다")
        found = await self._llm_model_repo.find_by_id(llm_model_id, request_id)
        if found is None:
            raise ValueError(f"LLM 모델을 찾을 수 없습니다: {llm_model_id}")

    async def _replace_document_template(
        self,
        agent,
        request: UpdateAgentRequest,
        request_id: str,
    ) -> None:
        """확정 템플릿 교체: 기존 active soft-delete + 신규 저장 (D4 앱 레벨 정합)."""
        ensure_template_wiring(self._document_template_repo, self._source_archiver)
        plan = build_document_template_plan(
            request.document_template, agent.workers, self._max_template_slots
        )
        existing = await self._document_template_repo.find_active_by_agent_worker(
            agent.id, plan.worker_id, request_id
        )
        if existing is not None:
            await self._document_template_repo.soft_delete(existing.id, request_id)
        await persist_document_template(
            plan, agent.id,
            self._document_template_repo, self._source_archiver, request_id,
        )

    async def _replace_document_generation_type(
        self,
        agent,
        request: UpdateAgentRequest,
        request_id: str,
    ) -> None:
        """문서 유형 교체: 기존 active soft-delete + 신규 저장 (앱 레벨 정합)."""
        ensure_generation_type_wiring(self._document_generation_type_repo)
        plan = build_document_generation_type_plan(
            request.document_generation_type,
            agent.workers,
            self._max_generation_sections,
        )
        existing = (
            await self._document_generation_type_repo.find_active_by_agent_worker(
                agent.id, plan.worker_id, request_id
            )
        )
        if existing is not None:
            await self._document_generation_type_repo.soft_delete(
                existing.id, request_id
            )
        await persist_document_generation_type(
            plan, agent.id, self._document_generation_type_repo, request_id,
        )

    async def _apply_sub_agents(
        self,
        agent,
        configs,
        viewer_user_id: str | None,
        request_id: str,
    ) -> None:
        """서브에이전트 워커를 재구성하여 교체한다 (도구 워커는 보존)."""
        owner_id = viewer_user_id or agent.user_id
        dept_ids = await self._resolve_department_ids(owner_id, request_id)
        tool_count = sum(1 for w in agent.workers if w.worker_type == "tool")
        sub_workers = await self._sub_agent_builder.build(
            configs=configs,
            parent_user_id=owner_id,
            parent_department_ids=dept_ids,
            existing_tool_count=tool_count,
            request_id=request_id,
            parent_agent_id=agent.id,
        )
        agent.replace_sub_agents(sub_workers)
        AgentBuilderPolicy.validate_worker_count(agent.workers)

    async def _resolve_department_ids(
        self, user_id: str, request_id: str
    ) -> list[str]:
        if self._dept_repo is None:
            return []
        try:
            memberships = await self._dept_repo.find_departments_by_user(
                int(user_id), request_id
            )
        except (TypeError, ValueError):
            return []
        return [m.department_id for m in memberships]

    async def _validate_visibility_scope(
        self,
        requested: str,
        workers: list[WorkerDefinition],
        request_id: str,
        user_id: str,
        viewer_role: str,
    ) -> None:
        scopes = await self._lookup_collection_scopes(workers, request_id)
        scopes += await self._lookup_kb_scopes(
            workers, request_id, user_id, viewer_role
        )
        if not scopes:
            return
        clamped = VisibilityPolicy.clamp_visibility(requested, scopes)
        if clamped != requested:
            raise ValueError(
                f"컬렉션 scope 제한으로 visibility를 "
                f"'{requested}'로 설정할 수 없습니다. "
                f"최대 허용: '{clamped}'"
            )

    async def _lookup_collection_scopes(
        self, workers: list[WorkerDefinition], request_id: str
    ) -> list[str]:
        """kb-rag-filter D7: kb_id 워커는 KB scope가 지배 — 컬렉션 조회 제외."""
        names = [
            w.tool_config["collection_name"]
            for w in workers
            if w.tool_config
            and not w.tool_config.get("kb_id")
            and w.tool_config.get("collection_name")
        ]
        scopes: list[str] = []
        for name in names:
            perm = await self._perm_repo.find_by_collection_name(
                name, request_id
            )
            scopes.append(perm.scope.value if perm else "PERSONAL")
        return scopes

    async def _lookup_kb_scopes(
        self,
        workers: list[WorkerDefinition],
        request_id: str,
        user_id: str,
        viewer_role: str,
    ) -> list[str]:
        """kb-rag-filter D3/D7: kb_id 워커의 KB scope 수집."""
        kbs = await self._resolve_kbs(workers, request_id, user_id, viewer_role)
        return [kb.scope.value for kb in kbs.values()]

    async def _resolve_kbs(
        self,
        workers: list[WorkerDefinition],
        request_id: str,
        user_id: str,
        viewer_role: str,
    ) -> dict:
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
        kbs: dict = {}
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
    def _canonicalize_kb_collections(
        workers: list[WorkerDefinition], kbs: dict
    ) -> None:
        """kb-rag-filter D1: kb_id 워커의 collection_name을 물리 컬렉션으로 고정."""
        for w in workers:
            kb_id = w.tool_config.get("kb_id") if w.tool_config else None
            if kb_id:
                w.tool_config["collection_name"] = kbs[kb_id].collection_name

    @staticmethod
    def _owner_ref(user_id: str | None) -> int | None:
        """user_id(str) → KB owner_id(int) 비교용. 비정수 형식은 소유자 불일치."""
        try:
            return int(user_id)
        except (TypeError, ValueError):
            return None
