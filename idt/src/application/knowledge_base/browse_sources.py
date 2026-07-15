"""KB 저장 내용 조회 소스 헬퍼 — kb-content-browser Design §4.2 (D2, D7).

Qdrant(scroll)/ES(term filter) 두 저장소에서 payload dict 리스트를
동일 형태로 가져온다. chunk_id 폴백(point.id / ES _id) 처리 포함.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.application.doc_browse.chunk_assembler import SUMMARY_CHUNK_TYPES
from src.domain.elasticsearch.schemas import ESSearchQuery

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient
    from src.domain.elasticsearch.interfaces import (
        ElasticsearchRepositoryInterface,
    )

FETCH_LIMIT = 10_000

SOURCE_QDRANT = "qdrant"
SOURCE_ES = "es"

# 요약 본문 필드 — 메타 표시에서 제외 (D5)
SUMMARY_BODY_KEYS = ("content", "summary", "summary_text")


def to_int_or(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_summary_text(payload: dict) -> str:
    """ES(summary_text) / Qdrant(content·summary) 요약 본문 정규화 (D5)."""
    for key in ("summary_text", "summary", "content"):
        value = payload.get(key)
        if value:
            return str(value)
    return ""


def normalize_keywords(payload: dict) -> List[str]:
    raw = payload.get("summary_keywords") or payload.get("keywords") or []
    if isinstance(raw, list):
        return [str(k) for k in raw]
    return [str(raw)]


def summary_metadata(payload: dict) -> dict:
    return {
        k: str(v) for k, v in payload.items() if k not in SUMMARY_BODY_KEYS
    }


async def scroll_qdrant_payloads(
    client: "AsyncQdrantClient",
    collection_name: str,
    document_id: str,
    chunk_type: Optional[str] = None,
) -> List[dict]:
    must = [
        FieldCondition(key="document_id", match=MatchValue(value=document_id))
    ]
    if chunk_type is not None:
        must.append(
            FieldCondition(key="chunk_type", match=MatchValue(value=chunk_type))
        )
    points, _ = await client.scroll(
        collection_name=collection_name,
        scroll_filter=Filter(must=must),
        limit=FETCH_LIMIT,
        with_vectors=False,
    )
    payloads: List[dict] = []
    for point in points:
        payload = dict(point.payload or {})
        payload.setdefault("chunk_id", point.id)
        payloads.append(payload)
    return payloads


def build_es_query(
    kb_id: str,
    document_id: str,
    chunk_type: Optional[str] = None,
    exclude_summaries: bool = False,
    match_content: Optional[str] = None,
) -> dict:
    bool_query: dict = {
        "filter": [
            {"term": {"kb_id": kb_id}},
            {"term": {"document_id": document_id}},
        ]
    }
    if chunk_type is not None:
        bool_query["filter"].append({"term": {"chunk_type": chunk_type}})
    if exclude_summaries:
        bool_query["must_not"] = [
            {"terms": {"chunk_type": list(SUMMARY_CHUNK_TYPES)}}
        ]
    if match_content is not None:
        bool_query["must"] = [{"match": {"content": match_content}}]
    return {"bool": bool_query}


async def search_es_payloads(
    es_repo: "ElasticsearchRepositoryInterface",
    es_index: str,
    request_id: str,
    query: dict,
    size: int = FETCH_LIMIT,
) -> List[dict]:
    hits = await es_repo.search(
        ESSearchQuery(index=es_index, query=query, size=size), request_id
    )
    payloads: List[dict] = []
    for hit in hits:
        payload = dict(hit.source)
        payload.setdefault("chunk_id", hit.id)
        payloads.append(payload)
    return payloads
