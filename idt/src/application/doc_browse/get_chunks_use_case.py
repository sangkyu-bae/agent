from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, List, Optional, Set

from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.domain.doc_browse.schemas import (
    ChunkDetail,
    DocumentChunksResult,
    ParentChunkGroup,
)

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient
    from src.domain.logging.interfaces.logger_interface import LoggerInterface

EXCLUDED_META_KEYS: Set[str] = {
    "content",
    "chunk_id",
    "chunk_index",
    "chunk_type",
    "total_chunks",
}

SCROLL_BATCH_LIMIT = 10_000


class GetChunksUseCase:
    def __init__(
        self,
        qdrant_client: AsyncQdrantClient,
        logger: LoggerInterface,
    ) -> None:
        self._client = qdrant_client
        self._logger = logger

    async def execute(
        self,
        collection_name: str,
        document_id: str,
        include_parent: bool = False,
    ) -> DocumentChunksResult:
        self._logger.info(
            "Get chunks started",
            collection=collection_name,
            document_id=document_id,
            include_parent=include_parent,
        )
        try:
            points = await self._scroll_filtered(collection_name, document_id)
            if not points:
                return DocumentChunksResult(
                    document_id=document_id,
                    filename="unknown",
                    chunk_strategy="unknown",
                    total_chunks=0,
                )

            strategy = self._detect_strategy(points)
            filename = self._extract_filename(points)
            total = len(points)

            if strategy == "parent_child" and include_parent:
                parents = self._build_hierarchy(points)
                result = DocumentChunksResult(
                    document_id=document_id,
                    filename=filename,
                    chunk_strategy=strategy,
                    total_chunks=total,
                    parents=parents,
                )
            else:
                chunks = self._build_flat_list(points, strategy)
                result = DocumentChunksResult(
                    document_id=document_id,
                    filename=filename,
                    chunk_strategy=strategy,
                    total_chunks=total,
                    chunks=chunks,
                )

            self._logger.info(
                "Get chunks completed",
                collection=collection_name,
                document_id=document_id,
                total_chunks=total,
            )
            return result
        except Exception as e:
            self._logger.error(
                "Get chunks failed",
                exception=e,
                collection=collection_name,
                document_id=document_id,
            )
            raise

    async def _scroll_filtered(
        self, collection_name: str, document_id: str
    ) -> list:
        scroll_filter = Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id),
                )
            ]
        )
        points, _ = await self._client.scroll(
            collection_name=collection_name,
            scroll_filter=scroll_filter,
            limit=SCROLL_BATCH_LIMIT,
            with_vectors=False,
        )
        return list(points)

    @staticmethod
    def _detect_strategy(points: list) -> str:
        chunk_types = {(p.payload or {}).get("chunk_type", "") for p in points}
        if "parent" in chunk_types or "child" in chunk_types:
            return "parent_child"
        if "full" in chunk_types:
            return "full_token"
        if "semantic" in chunk_types:
            return "semantic"
        return "unknown"

    @staticmethod
    def _extract_filename(points: list) -> str:
        for p in points:
            name = (p.payload or {}).get("filename")
            if name:
                return str(name)
        return "unknown"

    @staticmethod
    def _extract_metadata(payload: dict) -> dict:
        return {
            k: str(v)
            for k, v in payload.items()
            if k not in EXCLUDED_META_KEYS
        }

    def _to_chunk_detail(self, point) -> ChunkDetail:
        payload = point.payload or {}
        return ChunkDetail(
            chunk_id=str(payload.get("chunk_id", point.id)),
            chunk_index=int(payload.get("chunk_index", 0)),
            chunk_type=str(payload.get("chunk_type", "")),
            content=str(payload.get("content", "")),
            metadata=self._extract_metadata(payload),
        )

    def _build_flat_list(
        self, points: list, strategy: str
    ) -> List[ChunkDetail]:
        if strategy == "parent_child":
            filtered = [
                p
                for p in points
                if (p.payload or {}).get("chunk_type") != "parent"
            ]
        else:
            filtered = points

        chunks = [self._to_chunk_detail(p) for p in filtered]
        chunks.sort(key=lambda c: c.chunk_index)
        return chunks

    def _build_hierarchy(self, points: list) -> List[ParentChunkGroup]:
        parents_raw = []
        children_by_parent: dict[str, list] = defaultdict(list)

        for p in points:
            payload = p.payload or {}
            ct = payload.get("chunk_type", "")
            if ct == "parent":
                parents_raw.append(p)
            else:
                parent_id = str(payload.get("parent_id", ""))
                children_by_parent[parent_id].append(p)

        parents_raw.sort(key=lambda p: int((p.payload or {}).get("chunk_index", 0)))

        groups: List[ParentChunkGroup] = []
        for p in parents_raw:
            payload = p.payload or {}
            pid = str(payload.get("chunk_id", p.id))
            children = [self._to_chunk_detail(c) for c in children_by_parent.get(pid, [])]
            children.sort(key=lambda c: c.chunk_index)
            groups.append(
                ParentChunkGroup(
                    chunk_id=pid,
                    chunk_index=int(payload.get("chunk_index", 0)),
                    chunk_type="parent",
                    content=str(payload.get("content", "")),
                    children=children,
                )
            )
        return groups
