"""ListAttachedSkillsUseCase: 에이전트에 부착된 Skill 목록 조회."""
from src.application.agent_skill.schemas import (
    ListAttachedSkillsResponse,
    to_item,
)
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AccessCheckInput, VisibilityPolicy
from src.domain.agent_skill.interfaces import AgentSkillRepositoryInterface
from src.domain.agent_skill.policies import SkillAttachPolicy
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListAttachedSkillsUseCase:
    def __init__(
        self,
        agent_skill_repo: AgentSkillRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        dept_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._links = agent_skill_repo
        self._agents = agent_repo
        self._dept_repo = dept_repo
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        request_id: str,
        *,
        viewer_user_id: str,
        viewer_role: str,
    ) -> ListAttachedSkillsResponse:
        self._logger.info(
            "ListAttachedSkillsUseCase start",
            request_id=request_id, agent_id=agent_id,
        )
        agent = await self._agents.find_by_id(agent_id, request_id)
        if agent is None or agent.status == "deleted":
            raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")
        await self._ensure_access(agent, viewer_user_id, viewer_role, request_id)

        skills = await self._links.list_attached_skills(agent_id, request_id)
        items = [to_item(s, idx) for idx, s in enumerate(skills)]
        return ListAttachedSkillsResponse(
            agent_id=agent_id,
            skills=items,
            total=len(items),
            max_attachable=SkillAttachPolicy.MAX_ATTACHED,
        )

    async def _ensure_access(
        self, agent, viewer_user_id: str, viewer_role: str, request_id: str
    ) -> None:
        dept_ids = await self._viewer_dept_ids(viewer_user_id, request_id)
        ctx = AccessCheckInput(
            agent_owner_id=agent.user_id,
            agent_visibility=agent.visibility,
            agent_department_id=agent.department_id,
            viewer_user_id=viewer_user_id,
            viewer_department_ids=dept_ids,
            viewer_role=viewer_role,
        )
        if not VisibilityPolicy.can_access(ctx):
            raise PermissionError("이 에이전트에 접근할 권한이 없습니다")

    async def _viewer_dept_ids(
        self, viewer_user_id: str, request_id: str
    ) -> list[str]:
        rows = await self._dept_repo.find_departments_by_user(
            int(viewer_user_id), request_id
        )
        return [r.department_id for r in rows]
