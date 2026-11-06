"""KbDefaultSettingRepository — MySQL 영속화 (agent-kb-quick-setup Design §9.4).

세션 주입, commit/rollback 금지(UseCase 단일 세션 규칙).
get(): 행이 없으면 기본값 행을 만들어 돌려준다(신규 DB·시드 누락 방어, multimodal
선례).
"""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.kb_default_setting.entities import KbDefaultSetting
from src.domain.kb_default_setting.interfaces import (
    KbDefaultSettingRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.kb_default_setting.models import (
    KB_DEFAULT_SETTING_ID,
    KbDefaultSettingModel,
)


class KbDefaultSettingRepository(KbDefaultSettingRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def get(self, request_id: str) -> KbDefaultSetting:
        row = await self._load_or_create(request_id)
        return self._to_domain(row)

    async def update(
        self, setting: KbDefaultSetting, request_id: str
    ) -> KbDefaultSetting:
        try:
            row = await self._load_or_create(request_id)
            row.default_embedding_model_id = setting.default_embedding_model_id
            row.updated_at = datetime.now(UTC).replace(tzinfo=None)
            await self._session.flush()
            self._logger.info(
                "KbDefaultSetting updated",
                request_id=request_id,
                default_embedding_model_id=setting.default_embedding_model_id,
            )
            return self._to_domain(row)
        except Exception as e:
            self._logger.error(
                "KbDefaultSetting update failed", exception=e, request_id=request_id
            )
            raise

    async def _load_or_create(self, request_id: str) -> KbDefaultSettingModel:
        stmt = select(KbDefaultSettingModel).where(
            KbDefaultSettingModel.id == KB_DEFAULT_SETTING_ID
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return row
        self._logger.warning(
            "KbDefaultSetting row missing — creating defaults", request_id=request_id
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        row = KbDefaultSettingModel(
            id=KB_DEFAULT_SETTING_ID, created_at=now, updated_at=now
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    @staticmethod
    def _to_domain(row: KbDefaultSettingModel) -> KbDefaultSetting:
        return KbDefaultSetting(
            default_embedding_model_id=row.default_embedding_model_id,
            updated_at=row.updated_at,
        )
