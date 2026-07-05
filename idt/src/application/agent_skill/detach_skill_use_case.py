"""DetachSkillUseCase: 에이전트에서 Skill 부착 해제 (멱등)."""
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_skill.interfaces import AgentSkillRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class DetachSkillUseCase:
    def __init__(
        self,
        agent_skill_repo: AgentSkillRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._links = agent_skill_repo
        self._agents = agent_repo
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        skill_id: str,
        request_id: str,
        *,
        viewer_user_id: str,
        viewer_role: str,
    ) -> None:
        self._logger.info(
            "DetachSkillUseCase start",
            request_id=request_id, agent_id=agent_id, skill_id=skill_id,
        )
        agent = await self._agents.find_by_id(agent_id, request_id)
        if agent is None or agent.status == "deleted":
            raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")
        if not (agent.user_id == viewer_user_id or viewer_role == "admin"):
            raise PermissionError("이 에이전트를 수정할 권한이 없습니다")

        await self._links.detach(agent_id, skill_id, request_id)
        self._logger.info(
            "DetachSkillUseCase done", request_id=request_id, agent_id=agent_id,
        )
