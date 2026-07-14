"""UpdateAgentUseCase: 시스템 프롬프트 / 이름 / 서브에이전트 / 문서 템플릿 수정."""
from src.application.agent_builder.document_template_binding import (
    build_document_template_plan,
    ensure_template_wiring,
    persist_document_template,
)
from src.application.agent_builder.schemas import UpdateAgentRequest, UpdateAgentResponse
from src.domain.document_extractor.policies import DEFAULT_MAX_SLOTS
from src.application.agent_builder.sub_agent_worker_builder import SubAgentWorkerBuilder
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
from src.domain.collection.permission_interfaces import CollectionPermissionRepositoryInterface
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.knowledge_base.interfaces import KnowledgeBaseRepositoryInterface
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


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
        kb_repo: KnowledgeBaseRepositoryInterface | None = None,
        llm_model_repo: LlmModelRepositoryInterface | None = None,
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
        # agent-builder-edit-mapping FR-5: llm_model_id 수정 시 존재 검증용
        self._llm_model_repo = llm_model_repo
        self._sub_agent_builder = SubAgentWorkerBuilder(repository, logger)

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

            if request.visibility is not None:
                await self._validate_visibility_scope(
                    request.visibility, agent.workers, request_id,
                    viewer_user_id or agent.user_id, viewer_role,
                )

            # agent-builder-edit-mapping FR-5: None = 모델 변경 안 함
            if request.llm_model_id is not None:
                await self._validate_llm_model(request.llm_model_id, request_id)

            agent.apply_update(
                system_prompt=request.system_prompt,
                name=request.name,
                visibility=request.visibility,
                department_id=request.department_id,
                temperature=request.temperature,
                max_iterations=request.max_iterations,
                llm_model_id=request.llm_model_id,
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
        # kb-rag-filter D7: kb_id 워커는 KB scope가 지배 — 물리 컬렉션 조회 제외.
        collection_names = [
            w.tool_config["collection_name"]
            for w in workers
            if w.tool_config
            and not w.tool_config.get("kb_id")
            and w.tool_config.get("collection_name")
        ]
        scopes: list[str] = []
        for name in collection_names:
            perm = await self._perm_repo.find_by_collection_name(
                name, request_id
            )
            scopes.append(perm.scope.value if perm else "PERSONAL")
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

    async def _lookup_kb_scopes(
        self,
        workers: list[WorkerDefinition],
        request_id: str,
        user_id: str,
        viewer_role: str,
    ) -> list[str]:
        """kb-rag-filter D3/D7: kb_id 워커의 KB scope 수집.

        미존재 → ValueError(400), 읽기권한 없음 → PermissionError(403).
        """
        kb_ids = {
            w.tool_config["kb_id"]
            for w in workers
            if w.tool_config and w.tool_config.get("kb_id")
        }
        if not kb_ids:
            return []
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
        scopes: list[str] = []
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
            scopes.append(kb.scope.value)
        return scopes

    @staticmethod
    def _owner_ref(user_id: str | None) -> int | None:
        """user_id(str) → KB owner_id(int) 비교용. 비정수 형식은 소유자 불일치."""
        try:
            return int(user_id)
        except (TypeError, ValueError):
            return None
