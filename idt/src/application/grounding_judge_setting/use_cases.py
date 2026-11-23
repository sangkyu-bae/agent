"""근거 판정 모델 설정 조회·수정 (Design §4.2).

조회는 "지금 실제로 쓰이는 모델"과 출처(admin/env/default)를 함께 돌려준다 —
해석 순서는 AdminConfiguredJudgeLlmProvider 와 같다(Design D-16).
"""

from __future__ import annotations

from src.application.llm_model.cache_invalidation import invalidate_llm_model_cache
from src.domain.grounding_judge_setting.exceptions import (
    JudgeModelKindInvalidError,
    JudgeModelNotFoundError,
)
from src.domain.grounding_judge_setting.models import (
    EffectiveJudgeModel,
    GroundingJudgeSetting,
    JudgeModelSource,
)
from src.domain.grounding_judge_setting.ports import GroundingJudgeSettingRepositoryPort
from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

SettingView = tuple[GroundingJudgeSetting, EffectiveJudgeModel | None]


class GroundingJudgeSettingUseCase:
    def __init__(
        self,
        *,
        setting_repo: GroundingJudgeSettingRepositoryPort,
        model_repo: LlmModelRepositoryInterface,
        provider: UtilityLLMProviderPort | None,
        env_model_name: str,
        logger: LoggerInterface,
    ) -> None:
        self._setting_repo = setting_repo
        self._model_repo = model_repo
        self._provider = provider
        self._env_model_name = env_model_name
        self._logger = logger

    async def get(self, request_id: str) -> SettingView:
        setting = await self._setting_repo.get(request_id)
        return setting, await self._effective(setting, request_id)

    async def update(
        self, model_id: str | None, *, actor_id: str, request_id: str
    ) -> SettingView:
        if model_id is not None:
            await self._validate(model_id, request_id)
        saved = await self._setting_repo.update(
            GroundingJudgeSetting(judge_llm_model_id=model_id, updated_by=actor_id),
            request_id,
        )
        # 저장은 이미 끝났다 — 무효화 실패는 경고만 남기고 TTL 로 수렴한다.
        await invalidate_llm_model_cache(
            self._provider, self._logger, request_id, model_id=model_id
        )
        self._logger.info(
            "grounding judge model changed",
            request_id=request_id,
            model_id=model_id,
            actor_id=actor_id,
        )
        return saved, await self._effective(saved, request_id)

    async def _validate(self, model_id: str, request_id: str) -> None:
        model = await self._model_repo.find_by_id(model_id, request_id)
        if model is None or not model.is_active:
            raise JudgeModelNotFoundError(model_id)
        if not model.is_chat_model:
            raise JudgeModelKindInvalidError(model_id)

    async def _effective(
        self, setting: GroundingJudgeSetting, request_id: str
    ) -> EffectiveJudgeModel | None:
        if setting.judge_llm_model_id:
            model = await self._model_repo.find_by_id(
                setting.judge_llm_model_id, request_id
            )
            if model is not None and model.is_active and model.is_chat_model:
                return _view(model, "admin")
        actives = await self._model_repo.list_active(request_id)
        env = next((m for m in actives if m.model_name == self._env_model_name), None)
        if self._env_model_name and env is not None:
            return _view(env, "env")
        default = await self._model_repo.find_default(request_id)
        return _view(default, "default") if default is not None else None


def _view(model: LlmModel, source: JudgeModelSource) -> EffectiveJudgeModel:
    return EffectiveJudgeModel(
        model_id=model.id,
        model_name=model.model_name,
        display_name=model.display_name,
        source=source,
    )
