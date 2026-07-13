"""Multi-Query Search UseCase."""
from typing import Any

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.multi_query.schemas import MultiQueryResult, PerQueryHits
from src.application.multi_query.workflow import MultiQueryRewriteWorkflow


class MultiQuerySearchUseCase:
    """Multi-Query 검색 진입점 UseCase."""

    def __init__(
        self,
        query_generator: Any,
        hybrid_search: Any,
        query_rewriter: Any,
        logger: LoggerInterface,
    ) -> None:
        self._query_generator = query_generator
        self._hybrid_search = hybrid_search
        self._query_rewriter = query_rewriter
        self._logger = logger

    async def execute(
        self,
        query: str,
        request_id: str,
        top_k: int = 10,
        collection_name: str | None = None,
        es_index: str | None = None,
        metadata_filter: dict[str, str] | None = None,
    ) -> MultiQueryResult:
        """Multi-Query 워크플로우 실행 후 결과 반환."""
        workflow = MultiQueryRewriteWorkflow(
            query_generator=self._query_generator,
            hybrid_search=self._hybrid_search,
            query_rewriter=self._query_rewriter,
            logger=self._logger,
            collection_name=collection_name,
            es_index=es_index,
            metadata_filter=metadata_filter,
        )

        state = await workflow.run(
            query=query,
            request_id=request_id,
            top_k=top_k,
        )

        # retrieval-observability D6: asyncio.gather 순서 보존을 전제로
        # generated_queries × per_query_results를 zip (실패 폴백 state는 빈 목록).
        per_query_hits = [
            PerQueryHits(query=q, hit_ids=[hit.id for hit in hits])
            for q, hits in zip(
                state["generated_queries"], state["per_query_results"]
            )
        ]

        return MultiQueryResult(
            original_query=query,
            query_type=state["query_type"],
            generated_queries=state["generated_queries"],
            results=state["fused_results"],
            total_found=len(state["fused_results"]),
            request_id=request_id,
            per_query_hits=per_query_hits,
        )
