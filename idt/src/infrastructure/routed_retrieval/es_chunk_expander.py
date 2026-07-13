"""EsChunkExpander — 3차 rawchunk 확장 (summary-routed-retrieval Design D5).

section_ref(=parent chunk_id)를 ES ids query 1회로 조 본문 조회.
rawchunk는 ES `_id` = chunk_id (Qdrant point id와 불일치 — 2단계 확인 사실)라
ES 직조회가 정확하고 저렴하다. 누락 ref는 제외 + warning.
"""
from src.domain.elasticsearch.interfaces import (
    ElasticsearchRepositoryInterface,
)
from src.domain.elasticsearch.schemas import ESSearchQuery
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.routed_retrieval.interfaces import ChunkExpanderInterface
from src.domain.routed_retrieval.schemas import (
    DocumentCandidate,
    RoutedChunk,
    RoutedScope,
    SectionCandidate,
)


class EsChunkExpander(ChunkExpanderInterface):
    def __init__(
        self,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        logger: LoggerInterface,
    ) -> None:
        self._es_repo = es_repo
        self._es_index = es_index
        self._logger = logger

    async def expand(
        self,
        sections: list[SectionCandidate],
        documents_by_id: dict[str, DocumentCandidate],
        scope: RoutedScope,
        request_id: str,
    ) -> list[RoutedChunk]:
        if not sections:
            return []
        refs = [section.section_ref for section in sections]
        hits = await self._es_repo.search(
            ESSearchQuery(
                index=self._es_index,
                query={"ids": {"values": refs}},
                size=len(refs),
            ),
            request_id,
        )
        by_id = {hit.id: hit for hit in hits}
        chunks: list[RoutedChunk] = []
        for section in sections:
            hit = by_id.get(section.section_ref)
            if hit is None:
                self._logger.warning(
                    "Routed parent chunk missing in ES",
                    request_id=request_id,
                    section_ref=section.section_ref,
                    document_id=section.document_id,
                )
                continue
            source = hit.source or {}
            document_id = section.document_id or str(
                source.get("document_id", "")
            )
            chunks.append(
                RoutedChunk(
                    section_ref=section.section_ref,
                    document_id=document_id,
                    content=str(source.get("content", "")),
                    score=section.score,
                    clause_title=section.clause_title,
                    document=documents_by_id.get(document_id),
                    section=section,
                )
            )
        return chunks
