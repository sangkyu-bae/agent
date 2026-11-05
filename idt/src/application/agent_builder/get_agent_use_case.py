"""GetAgentUseCase: 에이전트 정의 조회."""
from typing import TYPE_CHECKING

from src.application.tool_access.schemas import ToolAccessInfo
from src.application.tool_access.validation import tool_access_info
from src.application.agent_builder.document_generation_type_binding import (
    DOCUMENT_GENERATOR_TOOL_ID,
)
from src.application.agent_builder.schemas import (
    DocumentGenerationTypeInfo,
    DocumentSectionRequest,
    GetAgentResponse,
    WorkerInfo,
)
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AccessCheckInput, VisibilityPolicy
from src.domain.agent_skill.interfaces import AgentSkillRepositoryInterface
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.agent_opener.interfaces import AgentOpenerRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

if TYPE_CHECKING:
    from src.application.tool_access.resolver import ToolAccessResolver


class GetAgentUseCase:
    def __init__(
        self,
        repository: AgentDefinitionRepositoryInterface,
        dept_repository: DepartmentRepositoryInterface,
        logger: LoggerInterface,
        agent_skill_repo: AgentSkillRepositoryInterface | None = None,
        agent_middleware_repo=None,
        document_generation_type_repo=None,
        opener_repo: AgentOpenerRepositoryInterface | None = None,
        tool_access_resolver: "ToolAccessResolver | None" = None,
    ) -> None:
        self._repository = repository
        # tool-access-control FR-13: 붙은 도구의 조회자 기준 허용 여부 (미주입 시 None)
        self._tool_access_resolver = tool_access_resolver
        self._dept_repository = dept_repository
        self._logger = logger
        self._agent_skill_repo = agent_skill_repo
        # builtin-middleware D5: edit 폼 프라임용 스냅샷 조회 (미주입 시 빈 목록)
        self._agent_middleware_repo = agent_middleware_repo
        # doc-generator FR-12: edit 폼 프리필용 활성 유형 조회 (미주입 시 None)
        self._document_generation_type_repo = document_generation_type_repo
        # agent-opener D4.3: edit 폼 프라임용 (미주입 시 빈 목록)
        self._opener_repo = opener_repo

    async def execute(
        self,
        agent_id: str,
        request_id: str,
        viewer_user_id: str | None = None,
        viewer_role: str = "user",
    ) -> GetAgentResponse | None:
        self._logger.info(
            "GetAgentUseCase start", request_id=request_id, agent_id=agent_id
        )
        try:
            agent = await self._repository.find_by_id(agent_id, request_id)
            if agent is None:
                return None

            can_edit = False
            can_delete = False
            if viewer_user_id is not None:
                ctx = AccessCheckInput(
                    agent_owner_id=agent.user_id,
                    agent_visibility=agent.visibility,
                    agent_department_id=agent.department_id,
                    viewer_user_id=viewer_user_id,
                    viewer_department_ids=[],
                    viewer_role=viewer_role,
                )
                can_edit = VisibilityPolicy.can_edit(ctx)
                can_delete = VisibilityPolicy.can_delete(ctx)

            department_name: str | None = None
            if agent.department_id is not None:
                dept = await self._dept_repository.find_by_id(
                    agent.department_id, request_id
                )
                if dept is not None:
                    department_name = dept.name

            workers_info: list[WorkerInfo] = []
            for w in agent.workers:
                ref_name: str | None = None
                if w.worker_type == "sub_agent" and w.ref_agent_id:
                    sub = await self._repository.find_by_id(
                        w.ref_agent_id, request_id
                    )
                    ref_name = sub.name if sub else "(삭제됨)"
                workers_info.append(WorkerInfo(
                    tool_id=w.tool_id,
                    worker_id=w.worker_id,
                    description=w.description,
                    sort_order=w.sort_order,
                    tool_config=w.tool_config,
                    worker_type=w.worker_type,
                    ref_agent_id=w.ref_agent_id,
                    ref_agent_name=ref_name,
                ))

            skill_ids: list[str] = []
            if self._agent_skill_repo is not None:
                links = await self._agent_skill_repo.list_links(
                    agent_id, request_id
                )
                skill_ids = [l.skill_id for l in links]

            middleware_types: list[str] = []
            if self._agent_middleware_repo is not None:
                records = await self._agent_middleware_repo.list_by_agent(
                    agent_id, request_id
                )
                middleware_types = [r.middleware_type for r in records]

            openers: list[str] = []
            if self._opener_repo is not None:
                openers = await self._opener_repo.list_by_agent_id(
                    agent_id, request_id
                )

            generation_type_info = await self._load_generation_type_info(
                agent, request_id
            )
            tool_access = await self._load_tool_access(
                agent, viewer_user_id, request_id
            )

            return GetAgentResponse(
                agent_id=agent.id,
                name=agent.name,
                description=agent.description,
                system_prompt=agent.system_prompt,
                tool_ids=[w.tool_id for w in agent.workers if w.worker_type == "tool"],
                skill_ids=skill_ids,
                workers=workers_info,
                flow_hint=agent.flow_hint,
                llm_model_id=agent.llm_model_id,
                status=agent.status,
                visibility=agent.visibility,
                department_id=agent.department_id,
                department_name=department_name,
                temperature=agent.temperature,
                max_iterations=agent.max_iterations,
                token_limit=agent.token_limit,
                middleware_types=middleware_types,
                openers=openers,
                document_generation_type=generation_type_info,
                owner_user_id=agent.user_id,
                can_edit=can_edit,
                can_delete=can_delete,
                created_at=agent.created_at.isoformat(),
                updated_at=agent.updated_at.isoformat(),
                tool_access=tool_access,
            )
        except Exception as e:
            self._logger.error(
                "GetAgentUseCase failed", exception=e, request_id=request_id
            )
            raise

    async def _load_tool_access(
        self, agent, viewer_user_id: str | None, request_id: str
    ) -> list[ToolAccessInfo] | None:
        """tool-access-control FR-13 — 표시용이라 조회 실패는 상세 전체를 막지 않는다.

        판정은 저장·실행 경로가 따로 한다. 실패·미배선·조회자 미상은 None
        (기존 응답과 같은 형태 — 프론트는 None 이면 카탈로그 기준 표시로 강하).
        """
        if self._tool_access_resolver is None or viewer_user_id is None:
            return None
        try:
            access = await self._tool_access_resolver.for_user_id(
                viewer_user_id, request_id
            )
        except Exception as e:
            self._logger.warning(
                "tool access lookup failed — tool_access omitted",
                request_id=request_id, agent_id=agent.id, exception=e,
            )
            return None
        return tool_access_info(access, agent.workers)

    async def _load_generation_type_info(
        self, agent, request_id: str
    ) -> DocumentGenerationTypeInfo | None:
        """doc-generator FR-12: generator 워커의 활성 유형 → 프리필 스냅샷."""
        if self._document_generation_type_repo is None:
            return None
        worker = next(
            (
                w for w in agent.workers
                if w.worker_type == "tool"
                and w.tool_id == DOCUMENT_GENERATOR_TOOL_ID
            ),
            None,
        )
        if worker is None:
            return None
        gen_type = (
            await self._document_generation_type_repo.find_active_by_agent_worker(
                agent.id, worker.worker_id, request_id
            )
        )
        if gen_type is None:
            return None
        tool_config = worker.tool_config or {}
        return DocumentGenerationTypeInfo(
            name=gen_type.name,
            description=gen_type.description,
            sections=[
                DocumentSectionRequest(title=s.title, guidance=s.guidance)
                for s in gen_type.sections
            ],
            output_format=gen_type.output_format,
            mcp_html_to_doc_tool_id=tool_config.get(
                "mcp_html_to_doc_tool_id", ""
            ),
        )
