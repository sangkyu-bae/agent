"""QdrantDocumentRouter — 1차 문서 라우팅 (summary-routed-retrieval Design D3).

chunk_type=document_summary 벡터 검색(가드 bypass 자연 통과) top-K.
문서 요약 근거(summary/keywords/filename)를 payload에서 추출한다.
"""
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.routed_retrieval.interfaces import DocumentRouterInterface
from src.domain.routed_retrieval.schemas import DocumentCandidate, RoutedScope
from src.domain.vector.interfaces import VectorStoreInterface
from src.domain.vector.value_objects import SearchFilter
from src.infrastructure.routed_retrieval.payload_utils import (
    parse_keyword_list,
)

_DOC_SUMMARY_CHUNK_TYPE = "document_summary"


class QdrantDocumentRouter(DocumentRouterInterface):
    def __init__(
        self, vector_store: VectorStoreInterface, logger: LoggerInterface
    ) -> None:
        self._vector_store = vector_store
        self._logger = logger

    async def route(
        self,
        query_vector: list[float],
        scope: RoutedScope,
        top_k: int,
        request_id: str,
    ) -> list[DocumentCandidate]:
        metadata = {"chunk_type": _DOC_SUMMARY_CHUNK_TYPE}
        if scope.kb_id:
            metadata["kb_id"] = scope.kb_id
        docs = await self._vector_store.search_by_vector(
            vector=query_vector,
            top_k=top_k,
            filter=SearchFilter(metadata=metadata),
            collection_name=scope.collection_name,
        )
        candidates: list[DocumentCandidate] = []
        for doc in docs:
            md = doc.metadata or {}
            document_id = str(md.get("document_id", "")).strip()
            if not document_id:
                self._logger.warning(
                    "Document candidate skipped: missing document_id",
                    request_id=request_id,
                )
                continue
            candidates.append(
                DocumentCandidate(
                    document_id=document_id,
                    score=doc.score or 0.0,
                    summary=str(md.get("summary", doc.content or "")),
                    keywords=parse_keyword_list(md.get("keywords")),
                    filename=str(md.get("filename", "")),
                )
            )
        return candidates
