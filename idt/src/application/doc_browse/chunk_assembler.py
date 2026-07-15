"""청크 조립 공용 헬퍼 — kb-content-browser Design §4.2 (구현 순서 1).

GetChunksUseCase에서 추출한 전략 감지/계층 조립/flat 목록 로직.
입력은 payload dict 리스트 — Qdrant point payload와 ES hit source를
동일 형태로 정규화해서 넘긴다 (chunk_id 폴백은 호출측 책임).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set

from src.domain.doc_browse.schemas import (
    ChunkDetail,
    DocumentChunksResult,
    ParentChunkGroup,
)

EXCLUDED_META_KEYS: Set[str] = {
    "content",
    "chunk_id",
    "chunk_index",
    "chunk_type",
    "total_chunks",
}

SUMMARY_CHUNK_TYPES: tuple[str, ...] = ("section_summary", "document_summary")


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def exclude_summary_payloads(payloads: List[dict]) -> List[dict]:
    """요약 계층 청크 제외 (card-section-summary D9 / document-summary-routing D13)."""
    return [
        p for p in payloads if p.get("chunk_type") not in SUMMARY_CHUNK_TYPES
    ]


def detect_strategy(payloads: List[dict]) -> str:
    chunk_types = {p.get("chunk_type", "") for p in payloads}
    if "parent" in chunk_types or "child" in chunk_types:
        return "parent_child"
    if "full" in chunk_types:
        return "full_token"
    if "semantic" in chunk_types:
        return "semantic"
    return "unknown"


def extract_filename(payloads: List[dict]) -> str:
    for p in payloads:
        name = p.get("filename")
        if name:
            return str(name)
    return "unknown"


def extract_metadata(payload: dict) -> Dict[str, str]:
    return {
        k: str(v) for k, v in payload.items() if k not in EXCLUDED_META_KEYS
    }


def to_chunk_detail(payload: dict) -> ChunkDetail:
    return ChunkDetail(
        chunk_id=str(payload.get("chunk_id", "")),
        chunk_index=_to_int(payload.get("chunk_index", 0)),
        chunk_type=str(payload.get("chunk_type", "")),
        content=str(payload.get("content", "")),
        metadata=extract_metadata(payload),
    )


def build_flat_list(payloads: List[dict], strategy: str) -> List[ChunkDetail]:
    if strategy == "parent_child":
        filtered = [p for p in payloads if p.get("chunk_type") != "parent"]
    else:
        filtered = payloads

    chunks = [to_chunk_detail(p) for p in filtered]
    chunks.sort(key=lambda c: c.chunk_index)
    return chunks


def build_hierarchy(payloads: List[dict]) -> List[ParentChunkGroup]:
    parents_raw: List[dict] = []
    children_by_parent: dict[str, list] = defaultdict(list)

    for p in payloads:
        if p.get("chunk_type", "") == "parent":
            parents_raw.append(p)
        else:
            children_by_parent[str(p.get("parent_id", ""))].append(p)

    parents_raw.sort(key=lambda p: _to_int(p.get("chunk_index", 0)))

    groups: List[ParentChunkGroup] = []
    for p in parents_raw:
        pid = str(p.get("chunk_id", ""))
        children = [to_chunk_detail(c) for c in children_by_parent.get(pid, [])]
        children.sort(key=lambda c: c.chunk_index)
        groups.append(
            ParentChunkGroup(
                chunk_id=pid,
                chunk_index=_to_int(p.get("chunk_index", 0)),
                chunk_type="parent",
                content=str(p.get("content", "")),
                children=children,
            )
        )
    return groups


def assemble_chunks_result(
    document_id: str,
    payloads: List[dict],
    include_parent: bool,
    filename: Optional[str] = None,
) -> DocumentChunksResult:
    """요약 제외가 끝난 payload 리스트를 DocumentChunksResult로 조립한다."""
    if not payloads:
        return DocumentChunksResult(
            document_id=document_id,
            filename=filename or "unknown",
            chunk_strategy="unknown",
            total_chunks=0,
        )

    strategy = detect_strategy(payloads)
    resolved_filename = extract_filename(payloads)
    if resolved_filename == "unknown" and filename:
        resolved_filename = filename
    total = len(payloads)

    if strategy == "parent_child" and include_parent:
        return DocumentChunksResult(
            document_id=document_id,
            filename=resolved_filename,
            chunk_strategy=strategy,
            total_chunks=total,
            parents=build_hierarchy(payloads),
        )
    return DocumentChunksResult(
        document_id=document_id,
        filename=resolved_filename,
        chunk_strategy=strategy,
        total_chunks=total,
        chunks=build_flat_list(payloads, strategy),
    )
