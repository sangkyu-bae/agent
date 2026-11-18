"""그래프 RAG 전역 설정 조회·수정 (Design §4.1 settings, Plan FR-03).

PUT 은 노출 단계를 바꾸지 않는다 — 단계는 ChangeStageUseCase(이력·전환 조건) 전용.
값 검증은 GraphRagSettings VO 가 한다(ValueError → 라우터 422 GRAPH_SETTINGS_INVALID).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from src.domain.graph_rag.interfaces import (
    GraphRagSettingsRepositoryPort,
    GraphSettingsReaderPort,
)
from src.domain.graph_rag.value_objects import GraphRagSettings
from src.domain.logging.interfaces.logger_interface import LoggerInterface


@dataclass(frozen=True)
class GraphRagSettingsUpdate:
    extraction_enabled: bool
    jev_enabled: bool
    link_threshold: float
    new_threshold: float
    extraction_llm_model_id: str | None
    rejudge_llm_model_id: str | None
    concurrency: int
    max_llm_calls_per_doc: int
    candidate_top_k: int
    max_hops: int
    graph_rrf_weight: float
    retrieval_timeout_ms: int
    entity_types: tuple[str, ...]
    relation_types: tuple[str, ...]


class GraphRagSettingsUseCase:
    def __init__(
        self,
        repo: GraphRagSettingsRepositoryPort,
        reader: GraphSettingsReaderPort,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repo
        self._reader = reader
        self._logger = logger

    async def get(self, request_id: str) -> GraphRagSettings:
        return await self._repo.get(request_id)

    async def update(
        self, upd: GraphRagSettingsUpdate, request_id: str
    ) -> GraphRagSettings:
        current = await self._repo.get(request_id)
        new = dataclasses.replace(current, **dataclasses.asdict(upd))  # VO 검증
        saved = await self._repo.update(new, request_id)
        self._reader.invalidate()
        self._logger.info(
            "graph rag settings updated",
            request_id=request_id,
            extraction_enabled=saved.extraction_enabled,
            jev_enabled=saved.jev_enabled,
        )
        return saved
