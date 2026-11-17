"""graph_rag MySQL 저장소 (V086·V087).

Design Ref: graph-rag-foundation §3.3 — 세션 주입, commit/rollback 금지
(UseCase 단일 세션 규칙). 설정 행이 없으면 닫힌 기본값 행을 만든다(V065 선례).
DB 의 단계 값이 알 수 없는 문자열이면 off 로 읽는다(기본은 닫힘).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.graph_rag.interfaces import (
    GraphRagSettingsRepositoryPort,
    StageChangeRepositoryPort,
)
from src.domain.graph_rag.value_objects import (
    GraphRagSettings,
    RolloutStage,
    StageChange,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.graph_rag.models import (
    GRAPH_RAG_SETTING_ID,
    GraphRagSettingModel,
    GraphRagStageChangeModel,
)


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _stage(raw: str, logger: LoggerInterface) -> RolloutStage:
    try:
        return RolloutStage.from_string(raw)
    except ValueError:
        logger.warning("Unknown rollout_stage in DB — reading as off", raw=raw)
        return RolloutStage.OFF


class GraphRagSettingRepository(GraphRagSettingsRepositoryPort):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def get(self, request_id: str) -> GraphRagSettings:
        return self._to_domain(await self._load_or_create(request_id))

    async def update(
        self, settings: GraphRagSettings, request_id: str
    ) -> GraphRagSettings:
        row = await self._load_or_create(request_id)
        self._apply(row, settings)
        row.updated_at = _now_naive()
        await self._session.flush()
        self._logger.info(
            "GraphRagSetting updated",
            request_id=request_id,
            rollout_stage=settings.rollout_stage.value,
            extraction_enabled=settings.extraction_enabled,
            jev_enabled=settings.jev_enabled,
        )
        return self._to_domain(row)

    async def _load_or_create(self, request_id: str) -> GraphRagSettingModel:
        stmt = select(GraphRagSettingModel).where(
            GraphRagSettingModel.id == GRAPH_RAG_SETTING_ID
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return row
        self._logger.warning(
            "GraphRagSetting row missing — creating closed defaults",
            request_id=request_id,
        )
        now = _now_naive()
        row = GraphRagSettingModel(
            id=GRAPH_RAG_SETTING_ID, created_at=now, updated_at=now
        )
        self._apply(row, GraphRagSettings.defaults())
        self._session.add(row)
        await self._session.flush()
        return row

    @staticmethod
    def _apply(row: GraphRagSettingModel, s: GraphRagSettings) -> None:
        row.rollout_stage = s.rollout_stage.value
        row.extraction_enabled = s.extraction_enabled
        row.jev_enabled = s.jev_enabled
        row.link_threshold = Decimal(str(s.link_threshold))
        row.new_threshold = Decimal(str(s.new_threshold))
        row.extraction_llm_model_id = s.extraction_llm_model_id
        row.rejudge_llm_model_id = s.rejudge_llm_model_id
        row.concurrency = s.concurrency
        row.max_llm_calls_per_doc = s.max_llm_calls_per_doc
        row.candidate_top_k = s.candidate_top_k
        row.max_hops = s.max_hops
        row.graph_rrf_weight = Decimal(str(s.graph_rrf_weight))
        row.retrieval_timeout_ms = s.retrieval_timeout_ms
        row.entity_types = list(s.entity_types)
        row.relation_types = list(s.relation_types)

    def _to_domain(self, row: GraphRagSettingModel) -> GraphRagSettings:
        return GraphRagSettings(
            rollout_stage=_stage(row.rollout_stage, self._logger),
            extraction_enabled=bool(row.extraction_enabled),
            jev_enabled=bool(row.jev_enabled),
            link_threshold=float(row.link_threshold),
            new_threshold=float(row.new_threshold),
            extraction_llm_model_id=row.extraction_llm_model_id,
            rejudge_llm_model_id=row.rejudge_llm_model_id,
            concurrency=row.concurrency,
            max_llm_calls_per_doc=row.max_llm_calls_per_doc,
            candidate_top_k=row.candidate_top_k,
            max_hops=row.max_hops,
            graph_rrf_weight=float(row.graph_rrf_weight),
            retrieval_timeout_ms=row.retrieval_timeout_ms,
            entity_types=tuple(row.entity_types or ()),
            relation_types=tuple(row.relation_types or ()),
            updated_at=row.updated_at,
        )


class GraphRagStageChangeRepository(StageChangeRepositoryPort):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def add(self, change: StageChange, request_id: str) -> None:
        self._session.add(
            GraphRagStageChangeModel(
                id=change.id,
                from_stage=change.from_stage.value,
                to_stage=change.to_stage.value,
                changed_by=change.changed_by,
                eval_baseline_run_id=change.eval_baseline_run_id,
                eval_graph_run_id=change.eval_graph_run_id,
                force_reason=change.force_reason,
                created_at=change.created_at.astimezone(UTC).replace(tzinfo=None),
            )
        )
        await self._session.flush()
        self._logger.info(
            "GraphRag stage changed",
            request_id=request_id,
            from_stage=change.from_stage.value,
            to_stage=change.to_stage.value,
            forced=change.force_reason is not None,
        )

    async def list_recent(self, limit: int, request_id: str) -> list[StageChange]:
        stmt = (
            select(GraphRagStageChangeModel)
            .order_by(GraphRagStageChangeModel.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            StageChange(
                id=r.id,
                from_stage=_stage(r.from_stage, self._logger),
                to_stage=_stage(r.to_stage, self._logger),
                changed_by=r.changed_by,
                eval_baseline_run_id=r.eval_baseline_run_id,
                eval_graph_run_id=r.eval_graph_run_id,
                force_reason=r.force_reason,
                created_at=r.created_at.replace(tzinfo=UTC),
            )
            for r in rows
        ]
