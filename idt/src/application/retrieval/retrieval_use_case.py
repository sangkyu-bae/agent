"""Retrieval use case for document search based on user queries.

Orchestrates: query rewriting → vector retrieval → compression → result mapping.
"""
from typing import Callable, Optional

from langchain_core.documents import Document as LangChainDocument

from src.domain.collection.schemas import ActionType
from src.domain.retrieval.schemas import (
    RetrievalRequest,
    RetrievalResult,
    RetrievedDocument,
)
from src.domain.retrieval.policies import RetrievalPolicy
from src.domain.retriever.value_objects.metadata_filter import MetadataFilter
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.retriever.parent_child_retriever import ParentChildRetriever


class RetrievalUseCase:
    """Use case for retrieving documents based on user queries.

    Supports:
    - Optional query rewriting via QueryRewriterUseCase
    - Child-first retrieval with parent context (ParentChildRetriever)
    - LLM-based relevance compression (DocumentCompressorInterface)
    - Metadata filtering by user_id and document_id
    """

    def __init__(
        self,
        retriever: ParentChildRetriever,
        compressor=None,
        query_rewriter=None,
        logger: Optional[LoggerInterface] = None,
        activity_log_factory: Optional[Callable] = None,
        collection_name: str = "documents",
    ) -> None:
        self._retriever = retriever
        self._compressor = compressor
        self._query_rewriter = query_rewriter
        self._logger = logger
        self._activity_log_factory = activity_log_factory
        self._collection_name = collection_name

    async def execute(self, request: RetrievalRequest) -> RetrievalResult:
        """Execute document retrieval for the given request.

        Args:
            request: RetrievalRequest with query and options.

        Returns:
            RetrievalResult with matching documents.

        Raises:
            ValueError: If query violates policy constraints.
        """
        RetrievalPolicy.validate_query(request.query)

        top_k = RetrievalPolicy.clamp_top_k(request.top_k)

        if self._logger:
            self._logger.info(
                "Retrieval started",
                request_id=request.request_id,
                query_len=len(request.query),
                top_k=top_k,
                use_parent_context=request.use_parent_context,
                use_compression=request.use_compression,
            )

        try:
            search_query = request.query
            rewritten_query: Optional[str] = None

            if request.use_query_rewrite and self._query_rewriter is not None:
                rewritten = await self._query_rewriter.rewrite(
                    query=request.query,
                    request_id=request.request_id,
                )
                search_query = rewritten.rewritten_query
                rewritten_query = rewritten.rewritten_query

            filters = MetadataFilter(
                user_id=request.user_id,
                document_id=request.document_id,
            )

            if request.use_parent_context:
                pc_results = await self._retriever.retrieve_with_parent(
                    query=search_query,
                    top_k=top_k,
                    filters=filters,
                )

                if request.use_compression and self._compressor is not None:
                    lc_docs = [
                        LangChainDocument(
                            page_content=r.child.content,
                            metadata=r.child.metadata,
                        )
                        for r in pc_results
                    ]
                    compressed = await self._compressor.compress(lc_docs, search_query)
                    compressed_contents = {d.page_content for d in compressed}
                    pc_results = [
                        r for r in pc_results
                        if r.child.content in compressed_contents
                    ]

                documents = [
                    RetrievedDocument(
                        id=str(r.child.id) if r.child.id else "",
                        content=r.child.content,
                        score=r.score,
                        metadata=r.child.metadata,
                        parent_content=r.parent.content,
                    )
                    for r in pc_results
                ]
            else:
                docs_with_scores = await self._retriever.retrieve_with_scores(
                    query=search_query,
                    top_k=top_k,
                    filters=filters,
                )

                if request.use_compression and self._compressor is not None:
                    lc_docs = [
                        LangChainDocument(
                            page_content=d.content,
                            metadata=d.metadata,
                        )
                        for d, _ in docs_with_scores
                    ]
                    compressed = await self._compressor.compress(lc_docs, search_query)
                    compressed_contents = {d.page_content for d in compressed}
                    docs_with_scores = [
                        (d, s) for d, s in docs_with_scores
                        if d.content in compressed_contents
                    ]

                documents = [
                    RetrievedDocument(
                        id=str(doc.id) if doc.id else "",
                        content=doc.content,
                        score=score,
                        metadata=doc.metadata,
                        parent_content=None,
                    )
                    for doc, score in docs_with_scores
                ]

            result = RetrievalResult(
                query=request.query,
                rewritten_query=rewritten_query,
                documents=documents,
                total_found=len(documents),
                request_id=request.request_id,
            )

            if self._logger:
                self._logger.info(
                    "Retrieval completed",
                    request_id=request.request_id,
                    total_found=result.total_found,
                )

            await self._log_activity(
                action=ActionType.SEARCH,
                request_id=request.request_id,
                user_id=request.user_id,
                detail={
                    "query": request.query[:200],
                    "top_k": top_k,
                    "results_count": result.total_found,
                },
            )

            return result

        except ValueError:
            raise
        except Exception as e:
            if self._logger:
                self._logger.error(
                    "Retrieval failed",
                    exception=e,
                    request_id=request.request_id,
                )
            raise

    async def _log_activity(
        self,
        action: ActionType,
        request_id: str,
        user_id: str | None = None,
        detail: dict | None = None,
    ) -> None:
        if self._activity_log_factory is None:
            return
        try:
            service = self._activity_log_factory()
            await service.log(
                collection_name=self._collection_name,
                action=action,
                request_id=request_id,
                user_id=user_id,
                detail=detail,
            )
        except Exception:
            pass
