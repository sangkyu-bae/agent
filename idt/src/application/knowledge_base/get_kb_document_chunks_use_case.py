"""GetKbDocumentChunksUseCase — KB 스코프 청크 조회 + 소스별 검색 (kb-content-browser Design §4.2).

D3: q 검색은 선택 저장소 기준 — es는 match(nori), qdrant는 부분일치(contains).
계층 조립은 chunk_assembler 공용 헬퍼 재사용.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Set

from src.application.doc_browse.chunk_assembler import (
    assemble_chunks_result,
    exclude_summary_payloads,
)
from src.application.knowledge_base.browse_sources import (
    SOURCE_QDRANT,
    build_es_query,
    scroll_qdrant_payloads,
    search_es_payloads,
)
from src.application.knowledge_base.content_browse_guard import KbDocumentGuard
from src.domain.auth.entities import User
from src.domain.doc_browse.schemas import (
    ChunkDetail,
    DocumentChunksResult,
    ParentChunkGroup,
)
from src.domain.knowledge_base.browse_schemas import KbDocumentChunksResult

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient
    from src.domain.elasticsearch.interfaces import (
        ElasticsearchRepositoryInterface,
    )
    from src.domain.logging.interfaces.logger_interface import LoggerInterface

_SEARCH_MODE_BY_SOURCE = {SOURCE_QDRANT: "contains", "es": "match"}


class GetKbDocumentChunksUseCase:
    def __init__(
        self,
        guard: KbDocumentGuard,
        qdrant_client: "AsyncQdrantClient",
        es_repo: "ElasticsearchRepositoryInterface",
        es_index: str,
        logger: "LoggerInterface",
    ) -> None:
        self._guard = guard
        self._client = qdrant_client
        self._es_repo = es_repo
        self._es_index = es_index
        self._logger = logger

    async def execute(
        self,
        kb_id: str,
        document_id: str,
        source: str,
        include_parent: bool,
        q: Optional[str],
        user: User,
        request_id: str,
    ) -> KbDocumentChunksResult:
        ctx = await self._guard.ensure(kb_id, document_id, user, request_id)

        if source == SOURCE_QDRANT:
            payloads = exclude_summary_payloads(
                await scroll_qdrant_payloads(
                    self._client, ctx.collection_name, document_id
                )
            )
            matched_ids = self._contains_ids(payloads, q)
        else:
            payloads = await search_es_payloads(
                self._es_repo,
                self._es_index,
                request_id,
                build_es_query(kb_id, document_id, exclude_summaries=True),
            )
            matched_ids = await self._es_match_ids(kb_id, document_id, q, request_id)

        assembled = assemble_chunks_result(
            document_id, payloads, include_parent, filename=ctx.filename
        )
        result = self._finalize(assembled, source, q, matched_ids)
        self._logger.info(
            "KB document chunks fetched",
            request_id=request_id,
            kb_id=kb_id,
            document_id=document_id,
            source=source,
            total_chunks=result.total_chunks,
            search_mode=result.search_mode,
        )
        return result

    @staticmethod
    def _contains_ids(
        payloads: List[dict], q: Optional[str]
    ) -> Optional[Set[str]]:
        if q is None:
            return None
        needle = q.lower()
        return {
            str(p.get("chunk_id", ""))
            for p in payloads
            if needle in str(p.get("content", "")).lower()
        }

    async def _es_match_ids(
        self, kb_id: str, document_id: str, q: Optional[str], request_id: str
    ) -> Optional[Set[str]]:
        if q is None:
            return None
        hits = await search_es_payloads(
            self._es_repo,
            self._es_index,
            request_id,
            build_es_query(
                kb_id, document_id, exclude_summaries=True, match_content=q
            ),
        )
        return {str(p.get("chunk_id", "")) for p in hits}

    def _finalize(
        self,
        assembled: DocumentChunksResult,
        source: str,
        q: Optional[str],
        matched_ids: Optional[Set[str]],
    ) -> KbDocumentChunksResult:
        chunks = assembled.chunks
        parents = assembled.parents
        total = assembled.total_chunks
        if q is not None and matched_ids is not None:
            if parents is not None:
                parents = self._filter_groups(parents, matched_ids)
                total = sum(1 + len(g.children) for g in parents)
            else:
                chunks = [c for c in chunks if c.chunk_id in matched_ids]
                total = len(chunks)
        return KbDocumentChunksResult(
            source=source,
            search_mode=_SEARCH_MODE_BY_SOURCE[source] if q is not None else None,
            document_id=assembled.document_id,
            filename=assembled.filename,
            chunk_strategy=assembled.chunk_strategy,
            total_chunks=total,
            chunks=chunks,
            parents=parents,
        )

    @staticmethod
    def _filter_groups(
        parents: List[ParentChunkGroup], matched_ids: Set[str]
    ) -> List[ParentChunkGroup]:
        """매칭 그룹만 유지 — parent 매칭 시 children 전체 유지 (Design §4.1)."""
        groups: List[ParentChunkGroup] = []
        for g in parents:
            parent_hit = g.chunk_id in matched_ids
            matched_children: List[ChunkDetail] = [
                c for c in g.children if c.chunk_id in matched_ids
            ]
            if not parent_hit and not matched_children:
                continue
            children = (
                g.children
                if parent_hit and not matched_children
                else matched_children
            )
            groups.append(
                ParentChunkGroup(
                    chunk_id=g.chunk_id,
                    chunk_index=g.chunk_index,
                    chunk_type=g.chunk_type,
                    content=g.content,
                    children=children,
                )
            )
        return groups
