"""본문 유사 후보 — 새 문서 앞부분과 같은 KB 기존 청크의 벡터 유사도.

Design Ref: document-revision §10.5 — 앞부분을 3토막으로 나눠 컬렉션 임베딩 모델로 임베딩하고,
kb_id 필터로 벡터 검색한다(개정 가드가 superseded 를 자동 제외). 문서별로 토막마다 최고
점수를 구하고, 그 평균을 content_score 로 쓴다(토막에 안 잡힌 문서는 0 으로 계산).
"""
from __future__ import annotations

from typing import Any

from src.domain.collection.interfaces import ActivityLogRepositoryInterface
from src.domain.document_revision.interfaces import HeadSimilaritySearchPort
from src.domain.embedding_model.interfaces import EmbeddingModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.vector.value_objects import SearchFilter

_MIN_SEGMENT_CHARS = 20


def split_head(text: str, parts: int) -> list[str]:
    """앞부분을 parts 토막으로. 토막이 너무 짧아지면(<20자) 나누지 않는다."""
    if not text:
        return []
    if len(text) < parts * _MIN_SEGMENT_CHARS:
        return [text]
    size = -(-len(text) // parts)
    return [text[i : i + size] for i in range(0, len(text), size)][:parts]


class CollectionHeadEmbedder:
    """컬렉션 생성 로그의 임베딩 모델로 임베딩 (UnifiedUploadUseCase 와 같은 해석 규칙)."""

    def __init__(
        self,
        activity_log_repo: ActivityLogRepositoryInterface,
        embedding_model_repo: EmbeddingModelRepositoryInterface,
        embedding_factory: Any,
    ) -> None:
        self._logs = activity_log_repo
        self._models = embedding_model_repo
        self._factory = embedding_factory

    async def embed(
        self, collection_name: str, texts: list[str], request_id: str
    ) -> list[list[float]]:
        logs = await self._logs.find_all(
            request_id=request_id,
            collection_name=collection_name,
            action="CREATE",
            limit=1,
        )
        model_name = (logs[0].detail or {}).get("embedding_model") if logs else None
        if not model_name:
            raise ValueError(
                f"Cannot determine embedding model for collection '{collection_name}'"
            )
        model = await self._models.find_by_model_name(model_name, request_id)
        if model is None:
            raise ValueError(f"Embedding model '{model_name}' not registered")
        embedding = self._factory.create_from_string(
            provider=model.provider, model_name=model.model_name
        )
        return await embedding.embed_documents(texts)


class QdrantHeadSimilaritySearch(HeadSimilaritySearchPort):
    def __init__(
        self,
        vector_store: Any,
        embedder: CollectionHeadEmbedder,
        logger: LoggerInterface,
        *,
        segments: int = 3,
        top_k: int = 30,
    ) -> None:
        self._store = vector_store
        self._embedder = embedder
        self._logger = logger
        self._segments = segments
        self._top_k = top_k

    async def search(
        self,
        *,
        collection_name: str,
        kb_id: str,
        head_text: str,
        request_id: str,
    ) -> dict[str, float]:
        parts = split_head(head_text, self._segments)
        if not parts:
            return {}
        vectors = await self._embedder.embed(collection_name, parts, request_id)
        best_per_part: list[dict[str, float]] = []
        for vector in vectors:
            docs = await self._store.search_by_vector(
                vector,
                self._top_k,
                SearchFilter(metadata={"kb_id": kb_id}),
                collection_name=collection_name,
            )
            best: dict[str, float] = {}
            for doc in docs:
                doc_id = doc.metadata.get("document_id")
                score = float(doc.score or 0.0)
                if doc_id and score > best.get(doc_id, 0.0):
                    best[doc_id] = score
            best_per_part.append(best)
        doc_ids = {d for best in best_per_part for d in best}
        return {
            d: sum(best.get(d, 0.0) for best in best_per_part) / len(best_per_part)
            for d in doc_ids
        }
