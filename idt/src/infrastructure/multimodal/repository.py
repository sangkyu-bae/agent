"""MultimodalSettingRepository — MySQL 영속화.

Design Ref: multimodal-extractor §9.4
— 세션 주입, commit/rollback 금지(UseCase 단일 세션 규칙).
get(): 행이 없으면 기본값 행을 만들어 돌려준다(신규 DB·시드 누락 방어).
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.multimodal.interfaces import MultimodalSettingRepository as _Port
from src.domain.multimodal.value_objects import MultimodalSettings
from src.infrastructure.multimodal.models import (
    MULTIMODAL_SETTING_ID,
    MultimodalSettingModel,
)


class MultimodalSettingRepository(_Port):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def get(self, request_id: str) -> MultimodalSettings:
        row = await self._load_or_create(request_id)
        return self._to_domain(row)

    async def update(
        self, settings: MultimodalSettings, request_id: str
    ) -> MultimodalSettings:
        try:
            row = await self._load_or_create(request_id)
            row.enabled = settings.enabled
            row.vision_model_id = settings.vision_model_id
            row.max_images_per_doc = settings.max_images_per_doc
            row.min_image_px = settings.min_image_px
            row.min_area_ratio = Decimal(str(settings.min_area_ratio))
            row.concurrency = settings.concurrency
            row.timeout_sec = settings.timeout_sec
            row.output_language = settings.output_language
            row.detail_level = settings.detail_level
            row.updated_at = datetime.now(UTC).replace(tzinfo=None)
            await self._session.flush()
            self._logger.info(
                "MultimodalSetting updated",
                request_id=request_id,
                vision_model_id=settings.vision_model_id,
                enabled=settings.enabled,
            )
            return self._to_domain(row)
        except Exception as e:
            self._logger.error(
                "MultimodalSetting update failed", exception=e, request_id=request_id
            )
            raise

    async def _load_or_create(self, request_id: str) -> MultimodalSettingModel:
        stmt = select(MultimodalSettingModel).where(
            MultimodalSettingModel.id == MULTIMODAL_SETTING_ID
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return row
        self._logger.warning(
            "MultimodalSetting row missing — creating defaults", request_id=request_id
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        row = MultimodalSettingModel(
            id=MULTIMODAL_SETTING_ID, created_at=now, updated_at=now
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    @staticmethod
    def _to_domain(row: MultimodalSettingModel) -> MultimodalSettings:
        return MultimodalSettings(
            id=row.id,
            enabled=bool(row.enabled),
            vision_model_id=row.vision_model_id,
            max_images_per_doc=row.max_images_per_doc,
            min_image_px=row.min_image_px,
            min_area_ratio=float(row.min_area_ratio),
            concurrency=row.concurrency,
            timeout_sec=row.timeout_sec,
            output_language=row.output_language,
            detail_level=row.detail_level,
            updated_at=row.updated_at,
        )
