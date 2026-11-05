"""kb-defaults DI 조립 (agent-kb-quick-setup Design §9.4).

main.py 의 DI 집중 규칙을 따르되, multimodal_di 선례처럼 wire 함수 1개로 묶는다.
UseCase 는 per-request 세션(get_session) 으로 조립한다.
"""
from collections.abc import Callable

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.kb_default_setting.use_case import KbDefaultSettingUseCase
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def build_kb_default_setting_use_case(
    session: AsyncSession, logger: LoggerInterface
) -> KbDefaultSettingUseCase:
    """세션 1개로 UseCase 조립 — 라우터 DI 와 KB 자동 배정기가 공유한다."""
    from src.infrastructure.embedding_model.repository import EmbeddingModelRepository
    from src.infrastructure.kb_default_setting.repository import (
        KbDefaultSettingRepository,
    )

    return KbDefaultSettingUseCase(
        settings_repo=KbDefaultSettingRepository(session, logger),
        embedding_model_repo=EmbeddingModelRepository(session=session, logger=logger),
        logger=logger,
    )


def wire_kb_defaults(
    app: FastAPI,
    *,
    get_session: Callable[..., AsyncSession],
    logger: LoggerInterface,
) -> None:
    """dependency_overrides 등록 + 라우터 2개 include. create_app() 에서 1회 호출."""
    from src.api.routes.admin_kb_defaults_router import (
        get_kb_default_setting_use_case,
    )
    from src.api.routes.admin_kb_defaults_router import router as admin_router
    from src.api.routes.kb_defaults_router import router as user_router

    def _factory(
        session: AsyncSession = Depends(get_session),
    ) -> KbDefaultSettingUseCase:
        return build_kb_default_setting_use_case(session, logger)

    app.dependency_overrides[get_kb_default_setting_use_case] = _factory
    app.include_router(admin_router)
    app.include_router(user_router)
