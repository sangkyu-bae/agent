"""ElasticsearchWikiSourceProvider: 원본 청크 조회·그룹핑 (LLM-WIKI-001, Phase 1/B).

ES에서 컬렉션(인덱스)의 청크를 조회해 group_field 기준으로 묶는다.
각 그룹이 하나의 위키 항목 후보가 되며, refs에는 추적용 청크 id를 담는다.
"""
from src.application.wiki.interfaces import WikiSourceProvider
from src.application.wiki.schemas import WikiSourceGroup
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.domain.elasticsearch.schemas import ESSearchQuery
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ElasticsearchWikiSourceProvider(WikiSourceProvider):
    """ES 청크를 주제(문서) 단위로 묶어 정제 소스로 제공한다."""

    def __init__(
        self,
        es_repo: ElasticsearchRepositoryInterface,
        logger: LoggerInterface,
        group_field: str = "source",
        chunk_fetch_limit: int = 200,
    ) -> None:
        self._es = es_repo
        self._logger = logger
        self._group_field = group_field
        self._limit = chunk_fetch_limit

    async def fetch_source_groups(
        self, agent_id: str, collection_name: str, max_articles: int, request_id: str
    ) -> list[WikiSourceGroup]:
        query = ESSearchQuery(
            index=collection_name,
            query={"match_all": {}},
            size=self._limit,
        )
        results = await self._es.search(query, request_id)
        grouped = self._group(results)
        groups = [
            WikiSourceGroup(topic_hint=key, texts=texts, refs=refs)
            for key, (texts, refs) in grouped.items()
        ]
        self._logger.info(
            "WikiSourceProvider fetched groups",
            request_id=request_id,
            agent_id=agent_id,
            group_count=len(groups),
        )
        return groups[:max_articles]

    def _group(self, results) -> dict:
        """group_field 기준으로 (texts, refs) 누적. 빈 content는 건너뛴다."""
        grouped: dict[str, tuple[list, list]] = {}
        for hit in results:
            content = (hit.source or {}).get("content", "")
            if not content or not content.strip():
                continue
            key = (hit.source or {}).get(self._group_field) or hit.id
            texts, refs = grouped.setdefault(key, ([], []))
            texts.append(content)
            refs.append(hit.id)
        return grouped
