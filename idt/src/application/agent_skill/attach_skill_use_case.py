"""AttachSkillUseCase: 에이전트에 Skill 부착.

권한 = 에이전트 수정권한(소유자/admin) ∧ skill 접근 가능(visibility).
두 도메인 정책(agent_builder.VisibilityPolicy / skill_builder.SkillVisibilityPolicy)을
이 application 계층에서 조합한다(도메인 간 직접 import 회피).
"""
from datetime import datetime

from src.application.agent_skill.schemas import (
    AttachSkillResponse,
    to_item,
)
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_skill.interfaces import AgentSkillRepositoryInterface
from src.domain.agent_skill.policies import SkillAttachPolicy
from src.domain.agent_skill.schemas import AgentSkillLink
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.skill_builder.interfaces import SkillRepositoryInterface
from src.domain.skill_builder.policies import (
    SkillAccessInput,
    SkillVisibilityPolicy,
)


class AttachSkillUseCase:
    def __init__(
        self,
        agent_skill_repo: AgentSkillRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        skill_repo: SkillRepositoryInterface,
        dept_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._links = agent_skill_repo
        self._agents = agent_repo
        self._skills = skill_repo
        self._dept_repo = dept_repo
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        skill_id: str,
        request_id: str,
        *,
        viewer_user_id: str,
        viewer_role: str,
    ) -> AttachSkillResponse:
        self._logger.info(
            "AttachSkillUseCase start",
            request_id=request_id, agent_id=agent_id, skill_id=skill_id,
        )
        agent = await self._agents.find_by_id(agent_id, request_id)
        if agent is None or agent.status == "deleted":
            raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")
        if not self._can_edit_agent(agent, viewer_user_id, viewer_role):
            raise PermissionError("이 에이전트를 수정할 권한이 없습니다")

        skill = await self._skills.find_by_id(skill_id, request_id)
        if skill is None or skill.status == "deleted":
            raise ValueError(f"스킬을 찾을 수 없습니다: {skill_id}")
        await self._ensure_skill_access(skill, viewer_user_id, viewer_role, request_id)

        links = await self._links.list_links(agent_id, request_id)
        SkillAttachPolicy.validate_attach(
            [l.skill_id for l in links], skill_id
        )

        link = AgentSkillLink(
            agent_id=agent_id,
            skill_id=skill_id,
            sort_order=len(links),
            created_at=datetime.utcnow(),
        )
        await self._links.attach(link, request_id)
        self._logger.info(
            "AttachSkillUseCase done", request_id=request_id, agent_id=agent_id,
        )
        return AttachSkillResponse(**to_item(skill, link.sort_order).model_dump())

    @staticmethod
    def _can_edit_agent(agent, viewer_user_id: str, viewer_role: str) -> bool:
        return agent.user_id == viewer_user_id or viewer_role == "admin"

    async def _ensure_skill_access(
        self, skill, viewer_user_id: str, viewer_role: str, request_id: str
    ) -> None:
        dept_ids = await self._viewer_dept_ids(viewer_user_id, request_id)
        ctx = SkillAccessInput(
            owner_id=skill.user_id,
            visibility=skill.visibility.value,
            department_id=skill.department_id,
            viewer_user_id=viewer_user_id,
            viewer_department_ids=dept_ids,
            viewer_role=viewer_role,
        )
        if not SkillVisibilityPolicy.can_access(ctx):
            raise PermissionError("이 스킬에 접근할 권한이 없습니다")

    async def _viewer_dept_ids(
        self, viewer_user_id: str, request_id: str
    ) -> list[str]:
        rows = await self._dept_repo.find_departments_by_user(
            int(viewer_user_id), request_id
        )
        return [r.department_id for r in rows]
