"""ListAvailableSubAgentsUseCase: 서브 에이전트로 사용 가능한 에이전트 목록.

사용 가능 후보 = 본인 소유 + 전체공개(public) + 부서공개(department, 동일 부서).
기존 `list_accessible(scope="all")`의 가시성 규칙을 그대로 재사용한다.
"""
from src.application.agent_builder.schemas import (
    AvailableSubAgentsResponse,
    SubAgentCandidate,
)
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

# 후보 조회 상한. 초과 시 truncated 로그를 남긴다.
_MAX_CANDIDATES = 200


class ListAvailableSubAgentsUseCase:
    def __init__(
        self,
        agent_repo: AgentDefinitionRepositoryInterface,
        dept_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._agent_repo = agent_repo
        self._dept_repo = dept_repo
        self._logger = logger

    async def execute(
        self, user_id: str, request_id: str
    ) -> AvailableSubAgentsResponse:
        self._logger.info(
            "ListAvailableSubAgentsUseCase start",
            request_id=request_id,
            user_id=user_id,
        )
        try:
            dept_ids = await self._resolve_department_ids(user_id, request_id)

            agents, total = await self._agent_repo.list_accessible(
                viewer_user_id=user_id,
                viewer_department_ids=dept_ids,
                scope="all",
                search=None,
                page=1,
                size=_MAX_CANDIDATES,
                request_id=request_id,
            )
            if total > _MAX_CANDIDATES:
                self._logger.info(
                    "ListAvailableSubAgentsUseCase truncated",
                    request_id=request_id,
                    total=total,
                    returned=_MAX_CANDIDATES,
                )

            candidates = [self._to_candidate(a, user_id) for a in agents]

            self._logger.info(
                "ListAvailableSubAgentsUseCase done",
                request_id=request_id,
                count=len(candidates),
            )
            return AvailableSubAgentsResponse(agents=candidates)
        except Exception as e:
            self._logger.error(
                "ListAvailableSubAgentsUseCase failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def _resolve_department_ids(
        self, user_id: str, request_id: str
    ) -> list[str]:
        try:
            memberships = await self._dept_repo.find_departments_by_user(
                int(user_id), request_id
            )
        except (TypeError, ValueError):
            return []
        return [m.department_id for m in memberships]

    @staticmethod
    def _to_candidate(
        agent: AgentDefinition, viewer_user_id: str
    ) -> SubAgentCandidate:
        if agent.user_id == viewer_user_id:
            source_type = "owned"
        elif agent.visibility == "public":
            source_type = "public"
        else:
            source_type = "department"
        return SubAgentCandidate(
            agent_id=agent.id,
            name=agent.name,
            description=agent.description,
            source_type=source_type,
            tool_ids=[
                w.tool_id for w in agent.workers if w.worker_type == "tool"
            ],
            has_sub_agents=any(
                w.worker_type == "sub_agent" for w in agent.workers
            ),
            llm_model_id=agent.llm_model_id,
            visibility=agent.visibility,
        )
