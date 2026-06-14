"""세션 팩토리 기반 LlmModelRepository 어댑터.

AGENT-OBS-001 §7: CostCalculator / ModelNameResolver는 RunAgentUseCase보다
긴 생명주기를 갖는다(애플리케이션 싱글톤). 따라서 per-request session에 의존할 수
없으므로 session_factory에서 매 호출마다 새 세션을 열어 위임한다.
"""
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.llm_model.llm_model_repository import LlmModelRepository


class SessionScopedLlmModelRepository(LlmModelRepositoryInterface):
    """애플리케이션 싱글톤 어댑터. 매 호출마다 새 세션을 열어 LlmModelRepository에 위임."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def save(self, model: LlmModel, request_id: str) -> LlmModel:
        async with self._session_factory() as session:
            async with session.begin():
                return await LlmModelRepository(session, self._logger).save(
                    model, request_id
                )

    async def find_by_id(
        self, model_id: str, request_id: str
    ) -> LlmModel | None:
        async with self._session_factory() as session:
            return await LlmModelRepository(session, self._logger).find_by_id(
                model_id, request_id
            )

    async def find_by_provider_and_name(
        self, provider: str, model_name: str, request_id: str
    ) -> LlmModel | None:
        async with self._session_factory() as session:
            return await LlmModelRepository(
                session, self._logger
            ).find_by_provider_and_name(provider, model_name, request_id)

    async def find_default(self, request_id: str) -> LlmModel | None:
        async with self._session_factory() as session:
            return await LlmModelRepository(session, self._logger).find_default(
                request_id
            )

    async def list_active(self, request_id: str) -> list[LlmModel]:
        async with self._session_factory() as session:
            return await LlmModelRepository(session, self._logger).list_active(
                request_id
            )

    async def list_all(self, request_id: str) -> list[LlmModel]:
        async with self._session_factory() as session:
            return await LlmModelRepository(session, self._logger).list_all(
                request_id
            )

    async def update(self, model: LlmModel, request_id: str) -> LlmModel:
        async with self._session_factory() as session:
            async with session.begin():
                return await LlmModelRepository(session, self._logger).update(
                    model, request_id
                )

    async def unset_all_defaults(self, request_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await LlmModelRepository(
                    session, self._logger
                ).unset_all_defaults(request_id)
