"""Elasticsearch repository implementation."""
from typing import Any, Optional

from elasticsearch import NotFoundError

from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.domain.elasticsearch.schemas import ESDocument, ESSearchQuery, ESSearchResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.elasticsearch.es_client import ElasticsearchClient


class ElasticsearchRepository(ElasticsearchRepositoryInterface):
    """ElasticsearchRepositoryInterface의 elasticsearch-py 구현체."""

    def __init__(self, client: ElasticsearchClient, logger: LoggerInterface) -> None:
        self._client = client
        self._logger = logger

    async def index(self, document: ESDocument, request_id: str) -> str:
        """문서 색인 (신규 또는 덮어쓰기)."""
        self._logger.info(
            "ES index start",
            request_id=request_id,
            index=document.index,
            doc_id=document.id,
        )
        try:
            es = self._client.get_client()
            resp = await es.index(
                index=document.index, id=document.id, document=document.body
            )
            self._logger.info(
                "ES index completed", request_id=request_id, doc_id=document.id
            )
            return resp["_id"]
        except Exception as e:
            self._logger.error(
                "ES index failed", exception=e, request_id=request_id, doc_id=document.id
            )
            raise

    async def bulk_index(self, documents: list[ESDocument], request_id: str) -> int:
        """문서 대량 색인."""
        self._logger.info(
            "ES bulk_index start", request_id=request_id, count=len(documents)
        )
        try:
            es = self._client.get_client()
            operations: list[Any] = []
            for doc in documents:
                operations.append({"index": {"_index": doc.index, "_id": doc.id}})
                operations.append(doc.body)

            resp = await es.bulk(operations=operations)

            if resp.get("errors"):
                failed = [
                    item
                    for item in resp["items"]
                    if item.get("index", {}).get("status", 200) >= 400
                ]
                self._logger.warning(
                    "ES bulk_index partial failure",
                    request_id=request_id,
                    failed_count=len(failed),
                )

            success_count = sum(
                1
                for item in resp["items"]
                if item.get("index", {}).get("status", 0) < 400
            )
            self._logger.info(
                "ES bulk_index completed",
                request_id=request_id,
                success_count=success_count,
            )
            return success_count
        except Exception as e:
            self._logger.error(
                "ES bulk_index failed", exception=e, request_id=request_id
            )
            raise

    async def get(
        self, index: str, doc_id: str, request_id: str
    ) -> Optional[dict[str, Any]]:
        """ID로 문서 조회."""
        try:
            es = self._client.get_client()
            resp = await es.get(index=index, id=doc_id)
            return resp["_source"]
        except NotFoundError:
            return None

    async def delete(self, index: str, doc_id: str, request_id: str) -> bool:
        """ID로 문서 삭제."""
        try:
            es = self._client.get_client()
            await es.delete(index=index, id=doc_id)
            return True
        except NotFoundError:
            return False
        except Exception as e:
            self._logger.error(
                "ES delete failed", exception=e, request_id=request_id, doc_id=doc_id
            )
            raise

    async def search(
        self, query: ESSearchQuery, request_id: str
    ) -> list[ESSearchResult]:
        """Query DSL 기반 검색."""
        self._logger.info(
            "ES search start", request_id=request_id, index=query.index
        )
        try:
            es = self._client.get_client()
            kwargs: dict[str, Any] = {
                "index": query.index,
                "query": query.query,
                "size": query.size,
                "from_": query.from_,
            }
            if query.source_fields:
                kwargs["source"] = query.source_fields

            resp = await es.search(**kwargs)
            hits = resp["hits"]["hits"]
            results = [
                ESSearchResult(
                    id=hit["_id"],
                    score=hit.get("_score") or 0.0,
                    source=hit["_source"],
                    index=hit["_index"],
                )
                for hit in hits
            ]
            self._logger.info(
                "ES search completed",
                request_id=request_id,
                result_count=len(results),
            )
            return results
        except Exception as e:
            self._logger.error(
                "ES search failed", exception=e, request_id=request_id
            )
            raise

    async def exists(self, index: str, doc_id: str, request_id: str) -> bool:
        """문서 존재 여부 확인."""
        try:
            es = self._client.get_client()
            result = await es.exists(index=index, id=doc_id)
            return bool(result)
        except NotFoundError:
            return False

    async def delete_by_query(
        self, index: str, query: dict[str, Any], request_id: str
    ) -> int:
        """쿼리 조건으로 문서 일괄 삭제."""
        self._logger.info(
            "ES delete_by_query start", request_id=request_id, index=index
        )
        try:
            es = self._client.get_client()
            resp = await es.delete_by_query(index=index, query=query)
            deleted = resp.get("deleted", 0)
            self._logger.info(
                "ES delete_by_query completed",
                request_id=request_id,
                deleted_count=deleted,
            )
            return deleted
        except Exception as e:
            self._logger.error(
                "ES delete_by_query failed", exception=e, request_id=request_id
            )
            raise
