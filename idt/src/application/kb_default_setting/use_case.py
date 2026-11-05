"""KbDefaultSettingUseCase — 기본 임베딩 모델 조회/교체/해석.

agent-kb-quick-setup Design §4.2 / §1.2 — 기본값은 DB 단일 행만 읽는다.
.env 폴백 없음(조용한 폴백은 FR-03 위반).
GET 은 끊어진 참조(삭제·비활성)를 warnings 로 알리고 configured=False 로 본다.
"""
from dataclasses import dataclass
from datetime import UTC, datetime

from src.domain.embedding_model.entity import EmbeddingModel
from src.domain.embedding_model.interfaces import (
    EmbeddingModelRepositoryInterface,
)
from src.domain.kb_default_setting.entities import KbDefaultSetting
from src.domain.kb_default_setting.errors import (
    EmbeddingModelInactiveError,
    EmbeddingModelNotFoundError,
    KbDefaultsNotConfiguredError,
)
from src.domain.kb_default_setting.interfaces import (
    KbDefaultSettingRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


@dataclass(frozen=True)
class KbDefaultsView:
    setting: KbDefaultSetting
    model: EmbeddingModel | None
    warnings: tuple[str, ...]

    @property
    def configured(self) -> bool:
        return self.model is not None and self.model.is_active


class KbDefaultSettingUseCase:
    def __init__(
        self,
        settings_repo: KbDefaultSettingRepositoryInterface,
        embedding_model_repo: EmbeddingModelRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._settings_repo = settings_repo
        self._model_repo = embedding_model_repo
        self._logger = logger

    async def get(self, request_id: str) -> KbDefaultsView:
        setting = await self._settings_repo.get(request_id)
        return await self._view(setting, request_id)

    async def update(self, model_id: int, request_id: str) -> KbDefaultsView:
        model = await self._model_repo.find_by_id(model_id, request_id)
        if model is None:
            raise EmbeddingModelNotFoundError()
        if not model.is_active:
            raise EmbeddingModelInactiveError()
        saved = await self._settings_repo.update(
            KbDefaultSetting(
                default_embedding_model_id=model_id,
                updated_at=datetime.now(UTC),
            ),
            request_id,
        )
        self._logger.info(
            "kb default embedding model updated",
            request_id=request_id,
            embedding_model_id=model_id,
            model_name=model.model_name,
        )
        return await self._view(saved, request_id)

    async def resolve_default_model(self, request_id: str) -> EmbeddingModel:
        """자동 컬렉션 생성용. 미설정·삭제·비활성은 전부 NotConfigured (FR-03)."""
        view = await self.get(request_id)
        if not view.configured or view.model is None:
            raise KbDefaultsNotConfiguredError()
        return view.model

    async def _view(
        self, setting: KbDefaultSetting, request_id: str
    ) -> KbDefaultsView:
        if setting.default_embedding_model_id is None:
            return KbDefaultsView(setting=setting, model=None, warnings=())
        model = await self._model_repo.find_by_id(
            setting.default_embedding_model_id, request_id
        )
        if model is None:
            return KbDefaultsView(
                setting=setting,
                model=None,
                warnings=(
                    f"기본 임베딩 모델(id={setting.default_embedding_model_id})이 "
                    "삭제되었습니다. 다시 선택해 주세요.",
                ),
            )
        if not model.is_active:
            return KbDefaultsView(
                setting=setting,
                model=model,
                warnings=(
                    f"기본 임베딩 모델 '{model.display_name}'이 비활성 상태입니다. "
                    "다시 선택해 주세요.",
                ),
            )
        return KbDefaultsView(setting=setting, model=model, warnings=())
