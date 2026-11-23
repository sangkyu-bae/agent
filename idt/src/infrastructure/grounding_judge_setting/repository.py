"""근거 판정 모델 설정 저장소 — 단일 행 (graph_rag_setting 선례).

commit/rollback 은 하지 않는다(세션 소유자 몫, CLAUDE.md §6).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.grounding_judge_setting.models import GroundingJudgeSetting
from src.domain.grounding_judge_setting.ports import GroundingJudgeSettingRepositoryPort
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.grounding_judge_setting.models import (
    GROUNDING_JUDGE_SETTING_ID,
    GroundingJudgeSettingModel,
)


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class GroundingJudgeSettingRepository(GroundingJudgeSettingRepositoryPort):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def get(self, request_id: str) -> GroundingJudgeSetting:
        return _to_domain(await self._load_or_create(request_id))

    async def update(
        self, setting: GroundingJudgeSetting, request_id: str
    ) -> GroundingJudgeSetting:
        row = await self._load_or_create(request_id)
        row.judge_llm_model_id = setting.judge_llm_model_id
        row.updated_by = setting.updated_by
        row.updated_at = _now_naive()
        await self._session.flush()
        self._logger.info(
            "GroundingJudgeSetting updated",
            request_id=request_id,
            judge_llm_model_id=setting.judge_llm_model_id,
        )
        return _to_domain(row)

    async def _load_or_create(self, request_id: str) -> GroundingJudgeSettingModel:
        stmt = select(GroundingJudgeSettingModel).where(
            GroundingJudgeSettingModel.id == GROUNDING_JUDGE_SETTING_ID
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return row
        self._logger.warning(
            "GroundingJudgeSetting row missing — creating empty row",
            request_id=request_id,
        )
        now = _now_naive()
        row = GroundingJudgeSettingModel(
            id=GROUNDING_JUDGE_SETTING_ID, created_at=now, updated_at=now
        )
        self._session.add(row)
        await self._session.flush()
        return row


def _to_domain(row: GroundingJudgeSettingModel) -> GroundingJudgeSetting:
    return GroundingJudgeSetting(
        judge_llm_model_id=row.judge_llm_model_id, updated_by=row.updated_by
    )
