"""ChunkAndIndexUseCase: 청킹 + 키워드 추출 + ES 색인 오케스트레이션."""
import uuid

from langchain_core.documents import Document as LangchainDocument

from src.application.chunk_and_index.schemas import (
    ChunkAndIndexRequest,
    ChunkAndIndexResult,
    IndexedChunk,
)
from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.domain.elasticsearch.schemas import ESDocument
from src.domain.keyword.interfaces import KeywordExtractorInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ChunkAndIndexUseCase:
    """문서를 청킹하고 키워드를 추출하여 Elasticsearch에 색인한다."""

    def __init__(
        self,
        chunking_strategy: ChunkingStrategy,
        keyword_extractor: KeywordExtractorInterface,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        logger: LoggerInterface,
    ) -> None:
        self._chunking_strategy = chunking_strategy
        self._keyword_extractor = keyword_extractor
        self._es_repo = es_repo
        self._es_index = es_index
        self._logger = logger

    async def execute(
        self, request: ChunkAndIndexRequest, request_id: str
    ) -> ChunkAndIndexResult:
        """청킹 → 키워드 추출 → ES bulk index 실행.

        Args:
            request: 청킹 및 색인 요청 파라미터
            request_id: 요청 추적 ID

        Returns:
            색인된 청크 정보를 포함한 결과
        """
        self._logger.info(
            "ChunkAndIndex started",
            request_id=request_id,
            document_id=request.document_id,
            strategy_type=request.strategy_type,
        )
        try:
            # 1. 청킹
            langchain_doc = LangchainDocument(
                page_content=request.content,
                metadata={
                    "document_id": request.document_id,
                    "user_id": request.user_id,
                    **request.metadata,
                },
            )
            chunks = self._chunking_strategy.chunk([langchain_doc])

            # 2. 청크별 키워드 추출 + ES 문서 빌드
            es_docs: list[ESDocument] = []
            indexed_chunks: list[IndexedChunk] = []

            for chunk in chunks:
                keyword_result = self._keyword_extractor.extract(
                    chunk.page_content, top_n=request.top_keywords
                )
                chunk_id = chunk.metadata.get("chunk_id") or str(uuid.uuid4())
                chunk_type = chunk.metadata.get("chunk_type", "full")

                body = {
                    "content": chunk.page_content,
                    "keywords": keyword_result.keywords,
                    "chunk_id": chunk_id,
                    "chunk_type": chunk_type,
                    "chunk_index": chunk.metadata.get("chunk_index", 0),
                    "total_chunks": chunk.metadata.get("total_chunks", 1),
                    "document_id": request.document_id,
                    "user_id": request.user_id,
                }
                if "parent_id" in chunk.metadata:
                    body["parent_id"] = chunk.metadata["parent_id"]

                es_docs.append(ESDocument(id=chunk_id, body=body, index=self._es_index))
                indexed_chunks.append(
                    IndexedChunk(
                        chunk_id=chunk_id,
                        chunk_type=chunk_type,
                        keywords=keyword_result.keywords,
                        content=chunk.page_content,
                    )
                )

            # 3. ES bulk index
            await self._es_repo.bulk_index(es_docs, request_id)

            self._logger.info(
                "ChunkAndIndex completed",
                request_id=request_id,
                document_id=request.document_id,
                total_chunks=len(indexed_chunks),
            )
            return ChunkAndIndexResult(
                document_id=request.document_id,
                user_id=request.user_id,
                total_chunks=len(indexed_chunks),
                indexed_chunks=indexed_chunks,
                request_id=request_id,
            )
        except Exception as e:
            self._logger.error(
                "ChunkAndIndex failed",
                exception=e,
                request_id=request_id,
                document_id=request.document_id,
            )
            raise
