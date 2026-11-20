"""근거 판정 모델 설정 조립 (answer-citation-verification §9.1, D-15·D-16).

- build_grounding_judge_provider: 기존 env 판정 공급자를 관리자 설정 공급자로 감싼다.
- wire_grounding_judge: 관리자 라우터 등록 + 유스케이스 의존성 연결.
인용 기능 스위치와 무관한 상시 기능이다 — 설정 테이블이 없거나 비면 env 공급자 그대로.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.grounding_judge_setting.provider import (
    AdminConfiguredJudgeLlmProvider,
)
from src.application.grounding_judge_setting.use_cases import (
    GroundingJudgeSettingUseCase,
)
from src.domain.llm.interfaces import LLMFactoryInterface, UtilityLLMProviderPort
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.grounding_judge_setting.repository import (
    GroundingJudgeSettingRepository,
)
from src.infrastructure.llm_model.llm_model_repository import LlmModelRepository


def build_grounding_judge_provider(
    *,
    fallback: UtilityLLMProviderPort,
    llm_factory: LLMFactoryInterface,
    session_factory: Callable[[], Any],
    logger: LoggerInterface,
    ttl_seconds: float,
) -> AdminConfiguredJudgeLlmProvider:
    return AdminConfiguredJudgeLlmProvider(
        session_factory=session_factory,
        setting_repo_factory=lambda s: GroundingJudgeSettingRepository(s, logger),
        model_repo_factory=lambda s: LlmModelRepository(session=s, logger=logger),
        llm_factory=llm_factory,
        fallback=fallback,
        logger=logger,
        ttl_seconds=ttl_seconds,
    )


def wire_grounding_judge(
    app: FastAPI,
    *,
    get_session: Callable[..., AsyncSession],
    provider: UtilityLLMProviderPort | None,
    env_model_name: str,
    logger: LoggerInterface,
) -> None:
    from src.api.routes import admin_grounding_judge_router as routes

    def _use_case(session: AsyncSession = Depends(get_session)):
        return GroundingJudgeSettingUseCase(
            setting_repo=GroundingJudgeSettingRepository(session, logger),
            model_repo=LlmModelRepository(session=session, logger=logger),
            provider=provider,
            env_model_name=env_model_name,
            logger=logger,
        )

    app.dependency_overrides[routes.get_grounding_judge_setting_use_case] = _use_case
    app.include_router(routes.router)
    logger.info("grounding judge setting wired", env_model_name=env_model_name)
