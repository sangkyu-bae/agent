"""agent-webhook UseCase 공용 접근 검사 헬퍼 (agent_schedule/access.py 동형)."""
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface


async def ensure_owned_agent(
    agent_repo: AgentDefinitionRepositoryInterface,
    agent_id: str,
    user_id: str,
    request_id: str,
) -> None:
    agent = await agent_repo.find_by_id(agent_id, request_id)
    if agent is None:
        raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")
    if agent.user_id != user_id:
        raise PermissionError("본인 소유 에이전트의 웹훅만 관리할 수 있습니다")
