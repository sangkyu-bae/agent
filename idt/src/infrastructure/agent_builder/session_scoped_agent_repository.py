"""세션 팩토리 기반 AgentDefinitionRepository 어댑터.

subagent-context-scope FR-11: WorkflowCompiler(앱 싱글톤)가 서브에이전트 정의를
런타임에 읽을 때 사용한다 (SessionScopedLlmModelRepository 패턴). per-request
세션에 묶일 수 없으므로 매 호출마다 새 세션을 열어 위임한다. 쓰기는 이 어댑터
경로에서 쓰이지 않지만 인터페이스 계약상 자체 트랜잭션으로 완결한다.
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_builder.agent_definition_repository import (
    AgentDefinitionRepository,
)


class SessionScopedAgentDefinitionRepository(AgentDefinitionRepositoryInterface):
    """매 호출마다 새 세션을 열어 AgentDefinitionRepository에 위임."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    def _repo(self, session: AsyncSession) -> AgentDefinitionRepository:
        return AgentDefinitionRepository(session, self._logger)

    async def save(self, agent: AgentDefinition, request_id: str) -> AgentDefinition:
        async with self._session_factory() as session:
            async with session.begin():
                return await self._repo(session).save(agent, request_id)

    async def find_by_id(
        self, agent_id: str, request_id: str
    ) -> AgentDefinition | None:
        async with self._session_factory() as session:
            return await self._repo(session).find_by_id(agent_id, request_id)

    async def find_by_id_with_status(
        self, agent_id: str, request_id: str
    ) -> AgentDefinition | None:
        async with self._session_factory() as session:
            return await self._repo(session).find_by_id_with_status(
                agent_id, request_id
            )

    async def update(self, agent: AgentDefinition, request_id: str) -> AgentDefinition:
        async with self._session_factory() as session:
            async with session.begin():
                return await self._repo(session).update(agent, request_id)

    async def list_by_user(
        self, user_id: str, request_id: str
    ) -> list[AgentDefinition]:
        async with self._session_factory() as session:
            return await self._repo(session).list_by_user(user_id, request_id)

    async def list_accessible(
        self,
        viewer_user_id: str,
        viewer_department_ids: list[str],
        scope: str,
        search: str | None,
        page: int,
        size: int,
        request_id: str,
    ) -> tuple[list[AgentDefinition], int]:
        async with self._session_factory() as session:
            return await self._repo(session).list_accessible(
                viewer_user_id, viewer_department_ids, scope, search,
                page, size, request_id,
            )

    async def soft_delete(self, agent_id: str, request_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await self._repo(session).soft_delete(agent_id, request_id)

    async def count_forks(self, source_agent_id: str, request_id: str) -> int:
        async with self._session_factory() as session:
            return await self._repo(session).count_forks(source_agent_id, request_id)

    async def count_subscribers(self, agent_id: str, request_id: str) -> int:
        async with self._session_factory() as session:
            return await self._repo(session).count_subscribers(agent_id, request_id)
