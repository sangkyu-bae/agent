"""후보 문서 앞부분 — ES 에서 document_id 청크를 chunk_index 순으로 이어 붙인다.

Design Ref: document-revision §10.5. parent 청크가 있으면 parent 만 쓴다(child 는 parent 의
부분 텍스트라 중복). 요약 청크는 제외. 후보는 이미 active 문서만이라 개정 가드 대상이 아니다.
"""
from __future__ import annotations

from src.domain.document_revision.interfaces import CandidateHeadReaderPort
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.domain.elasticsearch.schemas import ESSearchQuery
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_SUMMARY_TYPES = ["document_summary", "section_summary"]
_FETCH_SIZE = 40


class EsCandidateHeadReader(CandidateHeadReaderPort):
    def __init__(
        self,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        logger: LoggerInterface,
    ) -> None:
        self._es = es_repo
        self._index = es_index
        self._logger = logger

    async def read(self, document_id: str, max_chars: int, request_id: str) -> str:
        hits = await self._es.search(
            ESSearchQuery(
                index=self._index,
                query={
                    "bool": {
                        "filter": [{"term": {"document_id": document_id}}],
                        "must_not": [{"terms": {"chunk_type": _SUMMARY_TYPES}}],
                    }
                },
                size=_FETCH_SIZE,
            ),
            request_id,
        )
        parents = [h for h in hits if h.source.get("chunk_type") == "parent"]
        chosen = parents or list(hits)
        chosen.sort(key=lambda h: _index_of(h.source.get("chunk_index")))
        text = "\n".join(str(h.source.get("content", "")) for h in chosen)
        return text[:max_chars]


def _index_of(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1 << 30
