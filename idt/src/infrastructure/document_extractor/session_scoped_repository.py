"""세션 팩토리 기반 DocumentTemplateRepository 어댑터.

WorkflowCompiler(앱 싱글톤)의 합성 노드가 런타임에 템플릿을 읽을 때 사용
(SessionScopedLlmModelRepository 패턴). 쓰기 경로(create/update 편승)는
per-request DocumentTemplateRepository를 사용하므로 이 어댑터의 쓰기는
자체 트랜잭션으로 완결한다.
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.document_extractor.interfaces import (
    DocumentTemplateRepositoryInterface,
)
from src.domain.document_extractor.schemas import DocumentTemplate
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.document_extractor.document_template_repository import (
    DocumentTemplateRepository,
)


class SessionScopedDocumentTemplateRepository(DocumentTemplateRepositoryInterface):
    """매 호출마다 새 세션을 열어 DocumentTemplateRepository에 위임."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def save(
        self, template: DocumentTemplate, request_id: str
    ) -> DocumentTemplate:
        async with self._session_factory() as session:
            async with session.begin():
                return await DocumentTemplateRepository(
                    session, self._logger
                ).save(template, request_id)

    async def find_by_id(
        self, template_id: str, request_id: str
    ) -> DocumentTemplate | None:
        async with self._session_factory() as session:
            return await DocumentTemplateRepository(
                session, self._logger
            ).find_by_id(template_id, request_id)

    async def find_active_by_agent_worker(
        self, agent_id: str, worker_id: str, request_id: str
    ) -> DocumentTemplate | None:
        async with self._session_factory() as session:
            return await DocumentTemplateRepository(
                session, self._logger
            ).find_active_by_agent_worker(agent_id, worker_id, request_id)

    async def soft_delete(self, template_id: str, request_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await DocumentTemplateRepository(
                    session, self._logger
                ).soft_delete(template_id, request_id)

    async def soft_delete_by_agent(self, agent_id: str, request_id: str) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                return await DocumentTemplateRepository(
                    session, self._logger
                ).soft_delete_by_agent(agent_id, request_id)
