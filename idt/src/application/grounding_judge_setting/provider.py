"""관리자 설정 근거 판정 모델 공급자.

Design Ref: answer-citation-verification §2.2 D-15·D-16 — 해석 순서는
관리자 설정 모델(활성 채팅 모델) → 기존 env 공급자(GROUNDING_JUDGE_MODEL → 기본 모델).
설정 조회·모델 생성 실패도 env 공급자로 내려간다(예외를 올리지 않는다 — DR-7).
판정 어댑터는 이 공급자를 기존 UtilityLLMProvider 와 같은 포트로 받는다.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from langchain_core.language_models import BaseChatModel

from src.domain.grounding_judge_setting.ports import GroundingJudgeSettingRepositoryPort
from src.domain.llm.interfaces import LLMFactoryInterface, UtilityLLMProviderPort
from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_REQUEST_ID = "grounding-judge-provider"


class AdminConfiguredJudgeLlmProvider(UtilityLLMProviderPort):
    def __init__(
        self,
        *,
        session_factory: Callable[[], AbstractAsyncContextManager[Any]],
        setting_repo_factory: Callable[[Any], GroundingJudgeSettingRepositoryPort],
        model_repo_factory: Callable[[Any], LlmModelRepositoryInterface],
        llm_factory: LLMFactoryInterface,
        fallback: UtilityLLMProviderPort,
        logger: LoggerInterface,
        ttl_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._setting_repo_factory = setting_repo_factory
        self._model_repo_factory = model_repo_factory
        self._llm_factory = llm_factory
        self._fallback = fallback
        self._logger = logger
        self._ttl = ttl_seconds
        self._clock = clock
        self._resolved: LlmModel | None = None
        self._resolved_at: float | None = None
        self._instances: dict[tuple[str, str, float], BaseChatModel] = {}
        self._lock = asyncio.Lock()

    async def get(self, temperature: float = 0.0) -> BaseChatModel | None:
        model = await self._admin_model()
        if model is not None:
            llm = self._instance(model, temperature)
            if llm is not None:
                return llm
        return await self._fallback.get(temperature)

    async def invalidate(self) -> None:
        self._resolved, self._resolved_at = None, None
        self._instances.clear()
        await self._fallback.invalidate()

    async def _admin_model(self) -> LlmModel | None:
        if self._fresh():
            return self._resolved
        async with self._lock:
            if self._fresh():
                return self._resolved
            try:
                model = await self._resolve()
            except Exception as e:  # noqa: BLE001 — 실패는 env 공급자, 캐시하지 않음
                self._logger.warning(
                    "grounding judge setting read failed — using env model",
                    request_id=_REQUEST_ID,
                    exception=e,
                )
                return None
            self._resolved, self._resolved_at = model, self._clock()
            return model

    async def _resolve(self) -> LlmModel | None:
        async with self._session_factory() as session:
            setting = await self._setting_repo_factory(session).get(_REQUEST_ID)
            if not setting.judge_llm_model_id:
                return None
            model = await self._model_repo_factory(session).find_by_id(
                setting.judge_llm_model_id, _REQUEST_ID
            )
        if model is None or not model.is_active or not model.is_chat_model:
            self._logger.warning(
                "grounding judge model unusable — using env model",
                request_id=_REQUEST_ID,
                model_id=setting.judge_llm_model_id,
            )
            return None
        return model

    def _fresh(self) -> bool:
        return (
            self._resolved_at is not None
            and self._clock() - self._resolved_at < self._ttl
        )

    def _instance(self, model: LlmModel, temperature: float) -> BaseChatModel | None:
        key = (model.id, model.updated_at.isoformat(), temperature)
        cached = self._instances.get(key)
        if cached is not None:
            return cached
        try:
            llm = self._llm_factory.create(model, temperature=temperature)
        except Exception as e:  # noqa: BLE001 — 키 누락 등은 env 공급자로
            self._logger.warning(
                "grounding judge model instance failed — using env model",
                request_id=_REQUEST_ID,
                model_id=model.id,
                exception=e,
            )
            return None
        self._instances[key] = llm
        return llm
