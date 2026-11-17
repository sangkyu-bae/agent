"""관리자 점검 — 엔티티 목록·상세, 근거 정합성 (Design §4.1, FR-16, SC-2).

- 노출 단계 off 이면 GraphStageOffError(409). 백엔드가 없으면 503(저장소 예외 그대로).
- 상세의 언급 미리보기는 ES 에서 권한 필터 없이 읽는다(관리자 전용 API).
- 정합성: 그래프 청크 표본 중 ES 에 없는 청크(삭제 누락)를 센다.
"""

from __future__ import annotations

from dataclasses import replace

from src.domain.graph_rag.exceptions import GraphStageOffError
from src.domain.graph_rag.inspection import (
    MAX_DETAIL_MENTIONS,
    MAX_ENTITY_PAGE_SIZE,
    MAX_INTEGRITY_LISTED,
    MAX_INTEGRITY_SAMPLE,
    PREVIEW_CHARS,
    EntityDetail,
    EntitySummary,
    IntegrityReport,
)
from src.domain.graph_rag.interfaces import (
    EvidenceFetcherPort,
    GraphSettingsReaderPort,
    GraphStorePort,
)
from src.domain.graph_rag.value_objects import RolloutStage
from src.domain.logging.interfaces.logger_interface import LoggerInterface


async def ensure_stage_on(reader: GraphSettingsReaderPort) -> None:
    if (await reader.get()).rollout_stage is RolloutStage.OFF:
        raise GraphStageOffError("graph rag stage is off")


class InspectUseCase:
    def __init__(
        self,
        *,
        reader: GraphSettingsReaderPort,
        store: GraphStorePort,
        fetcher: EvidenceFetcherPort,
        logger: LoggerInterface,
    ) -> None:
        self._reader = reader
        self._store = store
        self._fetcher = fetcher
        self._logger = logger

    async def entities(
        self, *, query: str | None, type_: str | None, page: int, size: int
    ) -> tuple[list[EntitySummary], int]:
        await ensure_stage_on(self._reader)
        size = max(1, min(size, MAX_ENTITY_PAGE_SIZE))
        page = max(1, page)
        q = (query or "").strip() or None
        return await self._store.search_entities(
            q, type_ or None, (page - 1) * size, size
        )

    async def entity(self, entity_id: str, request_id: str) -> EntityDetail | None:
        await ensure_stage_on(self._reader)
        detail = await self._store.entity_detail(entity_id)
        if detail is None or not detail.mentions:
            return detail
        mentions = detail.mentions[:MAX_DETAIL_MENTIONS]
        hits = await self._fetcher.fetch(
            list({m.chunk_id for m in mentions}),
            hard_filter={},
            lenient_filter={},
            collection_name=None,
            es_index=None,
            request_id=request_id,
        )
        previews = {h.id: h.content[:PREVIEW_CHARS] for h in hits}
        detail.mentions = [
            replace(m, preview=previews.get(m.chunk_id, "")) for m in mentions
        ]
        return detail

    async def integrity(
        self, *, kb_id: str | None, sample: int, request_id: str
    ) -> IntegrityReport:
        await ensure_stage_on(self._reader)
        refs = await self._store.sample_chunks(
            kb_id, max(1, min(sample, MAX_INTEGRITY_SAMPLE))
        )
        found = await self._fetcher.fetch(
            [r.chunk_id for r in refs],
            hard_filter={},
            lenient_filter={},
            collection_name=None,
            es_index=None,
            request_id=request_id,
        )
        present = {h.id for h in found}
        missing = [r for r in refs if r.chunk_id not in present]
        report = IntegrityReport(
            checked=len(refs),
            missing=len(missing),
            missing_chunk_ids=tuple(r.chunk_id for r in missing[:MAX_INTEGRITY_LISTED]),
            missing_document_ids=tuple(sorted({r.document_id for r in missing}))[
                :MAX_INTEGRITY_LISTED
            ],
        )
        self._logger.info(
            "graph integrity checked",
            request_id=request_id,
            kb_id=kb_id,
            checked=report.checked,
            missing=report.missing,
        )
        return report
