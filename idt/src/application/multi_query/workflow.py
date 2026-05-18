"""LangGraph StateGraph 기반 Multi-Query Rewrite 워크플로우."""
import asyncio
from typing import Any

from langgraph.graph import StateGraph, END

from src.domain.hybrid_search.schemas import HybridSearchRequest, HybridSearchResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.multi_query.policy import MultiQueryFusionPolicy, MultiQueryPolicy
from src.domain.multi_query.schemas import MultiQueryState


class MultiQueryRewriteWorkflow:
    """Multi-Query Rewrite LangGraph 워크플로우.

    classify → (simple → simple_rewrite / complex|ambiguous → generate_queries)
    → parallel_search → fuse_results → END
    """

    def __init__(
        self,
        query_generator: Any,
        hybrid_search: Any,
        query_rewriter: Any,
        logger: LoggerInterface,
        collection_name: str | None = None,
        es_index: str | None = None,
        metadata_filter: dict[str, str] | None = None,
    ) -> None:
        self._query_generator = query_generator
        self._hybrid_search = hybrid_search
        self._query_rewriter = query_rewriter
        self._logger = logger
        self._collection_name = collection_name
        self._es_index = es_index
        self._metadata_filter = metadata_filter or {}
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        workflow = StateGraph(MultiQueryState)

        workflow.add_node("classify_query", self._classify_query_node)
        workflow.add_node("simple_rewrite", self._simple_rewrite_node)
        workflow.add_node("generate_queries", self._generate_queries_node)
        workflow.add_node("parallel_search", self._parallel_search_node)
        workflow.add_node("fuse_results", self._fuse_results_node)

        workflow.set_entry_point("classify_query")

        workflow.add_conditional_edges(
            "classify_query",
            self._after_classify,
            {
                "simple_rewrite": "simple_rewrite",
                "generate_queries": "generate_queries",
            },
        )

        workflow.add_edge("simple_rewrite", "parallel_search")
        workflow.add_edge("generate_queries", "parallel_search")
        workflow.add_edge("parallel_search", "fuse_results")
        workflow.add_edge("fuse_results", END)

        return workflow.compile()

    async def _classify_query_node(self, state: MultiQueryState) -> dict:
        query = state["original_query"]
        request_id = state["request_id"]

        query_type = MultiQueryPolicy.classify(query)

        self._logger.info(
            "Query classified",
            request_id=request_id,
            query_type=query_type,
        )

        return {"query_type": query_type, "status": "classifying"}

    def _after_classify(self, state: MultiQueryState) -> str:
        if state["query_type"] == "simple":
            return "simple_rewrite"
        return "generate_queries"

    async def _simple_rewrite_node(self, state: MultiQueryState) -> dict:
        query = state["original_query"]
        request_id = state["request_id"]

        try:
            result = await self._query_rewriter.rewrite(
                query=query, request_id=request_id
            )
            rewritten = result.rewritten_query
        except Exception as e:
            self._logger.warning(
                "Simple rewrite failed, using original query",
                exception=e,
                request_id=request_id,
            )
            rewritten = query

        return {
            "generated_queries": [rewritten],
            "status": "generating",
        }

    async def _generate_queries_node(self, state: MultiQueryState) -> dict:
        query = state["original_query"]
        request_id = state["request_id"]

        queries = await self._query_generator.generate(
            query=query,
            num_queries=MultiQueryPolicy.MAX_GENERATED_QUERIES,
            request_id=request_id,
        )

        self._logger.info(
            "Multi-queries generated",
            request_id=request_id,
            count=len(queries),
        )

        return {
            "generated_queries": queries,
            "status": "generating",
        }

    async def _parallel_search_node(self, state: MultiQueryState) -> dict:
        queries = state["generated_queries"]
        request_id = state["request_id"]
        top_k = state["top_k"]

        per_query_top_k = MultiQueryPolicy.calculate_per_query_top_k(
            top_k, len(queries)
        )

        async def _search_single(q: str) -> list[HybridSearchResult]:
            try:
                req = HybridSearchRequest(
                    query=q,
                    top_k=per_query_top_k,
                    bm25_top_k=per_query_top_k * 2,
                    vector_top_k=per_query_top_k * 2,
                    metadata_filter=self._metadata_filter,
                    collection_name=self._collection_name,
                    es_index=self._es_index,
                )
                resp = await self._hybrid_search.execute(req, request_id)
                return resp.results
            except Exception as e:
                self._logger.warning(
                    "Search failed for variant query",
                    exception=e,
                    request_id=request_id,
                    query=q,
                )
                return []

        tasks = [_search_single(q) for q in queries]
        per_query_results = await asyncio.gather(*tasks)

        self._logger.info(
            "Parallel search completed",
            request_id=request_id,
            query_count=len(queries),
            total_results=sum(len(r) for r in per_query_results),
        )

        return {
            "per_query_results": list(per_query_results),
            "status": "searching",
        }

    async def _fuse_results_node(self, state: MultiQueryState) -> dict:
        per_query_results = state["per_query_results"]
        top_k = state["top_k"]
        request_id = state["request_id"]

        fused = MultiQueryFusionPolicy.fuse(
            per_query_results=per_query_results,
            top_k=top_k,
        )

        self._logger.info(
            "Results fused",
            request_id=request_id,
            fused_count=len(fused),
        )

        return {
            "fused_results": fused,
            "status": "completed",
        }

    async def run(
        self,
        query: str,
        request_id: str,
        top_k: int = 10,
    ) -> MultiQueryState:
        """워크플로우 실행."""
        self._logger.info(
            "MultiQuery workflow started",
            request_id=request_id,
            query_preview=query[:50],
        )

        initial_state: MultiQueryState = {
            "original_query": query,
            "request_id": request_id,
            "top_k": top_k,
            "query_type": "",
            "generated_queries": [],
            "per_query_results": [],
            "fused_results": [],
            "errors": [],
            "status": "started",
        }

        try:
            result = await self._graph.ainvoke(initial_state)
            self._logger.info(
                "MultiQuery workflow completed",
                request_id=request_id,
                query_type=result["query_type"],
                result_count=len(result["fused_results"]),
            )
            return result
        except Exception as e:
            self._logger.error(
                "MultiQuery workflow failed",
                exception=e,
                request_id=request_id,
            )
            return {
                **initial_state,
                "status": "failed",
                "errors": [str(e)],
            }
