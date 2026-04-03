"""Ingest Document UseCase — parse + chunk + embed + store pipeline.

Orchestrates:
  1. Parser selection from registry
  2. PDF parsing via PDFParseUseCase
  3. Chunking via ChunkingStrategyFactory
  4. Embedding via EmbeddingInterface
  5. Vector storage via VectorStoreInterface
"""
from typing import Dict, List

from src.domain.ingest.schemas import IngestRequest, IngestResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.schemas import ParseDocumentRequest
from src.domain.vector.entities import Document as VectorDocument
from src.domain.vector.interfaces import EmbeddingInterface, VectorStoreInterface
from src.domain.vector.value_objects import DocumentId
from src.application.use_cases.pdf_parse_use_case import PDFParseUseCase
from src.infrastructure.chunking.chunking_factory import ChunkingStrategyFactory


class IngestDocumentUseCase:
    """Orchestrates the full PDF ingest pipeline.

    Accepts a parser registry so callers can select the parser at request time
    (e.g., "pymupdf" for fast local parsing, "llamaparser" for OCR/AI parsing).

    LOG-001 compliant: INFO on start/complete, ERROR with exception= on failure.
    """

    def __init__(
        self,
        parsers: Dict[str, PDFParserInterface],
        embedding: EmbeddingInterface,
        vectorstore: VectorStoreInterface,
        logger: LoggerInterface,
    ) -> None:
        self._parsers = parsers
        self._embedding = embedding
        self._vectorstore = vectorstore
        self._logger = logger

    async def ingest(self, request: IngestRequest) -> IngestResult:
        """Run the full ingest pipeline for a PDF file.

        Args:
            request: IngestRequest with file bytes and configuration

        Returns:
            IngestResult with document ID, chunk count, stored IDs

        Raises:
            ValueError: If parser_type is not in the registry
            Exception: Re-raises any pipeline exception after logging
        """
        if request.parser_type not in self._parsers:
            raise ValueError(
                f"Unknown parser_type: '{request.parser_type}'. "
                f"Available: {list(self._parsers.keys())}"
            )

        self._logger.info(
            "Ingest pipeline started",
            request_id=request.request_id,
            filename=request.filename,
            user_id=request.user_id,
            parser_type=request.parser_type,
            chunking_strategy=request.chunking_strategy,
        )

        try:
            # 1. Parse
            parser = self._parsers[request.parser_type]
            parse_uc = PDFParseUseCase(parser=parser, logger=self._logger)
            parse_result = await parse_uc.parse_from_bytes(
                ParseDocumentRequest(
                    filename=request.filename,
                    user_id=request.user_id,
                    request_id=request.request_id,
                    file_bytes=request.file_bytes,
                )
            )

            # 2. Chunk
            strategy = ChunkingStrategyFactory.create_strategy(
                request.chunking_strategy,
                chunk_size=request.chunk_size,
                chunk_overlap=request.chunk_overlap,
            )
            chunks = strategy.chunk(parse_result.documents)

            # 3. Embed
            texts = [c.page_content for c in chunks if c.page_content.strip()]
            vectors: List[List[float]] = await self._embedding.embed_documents(texts)

            # 4. Convert to domain vector documents
            domain_docs = self._to_vector_documents(chunks, vectors, request)

            # 5. Store
            stored_doc_ids = await self._vectorstore.add_documents(domain_docs)

        except Exception as exc:
            self._logger.error(
                "Ingest pipeline failed",
                exception=exc,
                request_id=request.request_id,
                filename=request.filename,
            )
            raise

        result = IngestResult(
            document_id=parse_result.document_id,
            filename=request.filename,
            user_id=request.user_id,
            total_pages=parse_result.total_pages,
            chunk_count=len(domain_docs),
            parser_used=parse_result.parser_used,
            chunking_strategy=strategy.get_strategy_name(),
            stored_ids=[did.value for did in stored_doc_ids],
            request_id=request.request_id,
        )

        self._logger.info(
            "Ingest pipeline completed",
            request_id=request.request_id,
            filename=request.filename,
            total_pages=result.total_pages,
            chunk_count=result.chunk_count,
        )

        return result

    def _to_vector_documents(
        self,
        chunks,
        vectors: List[List[float]],
        request: IngestRequest,
    ) -> List[VectorDocument]:
        """Convert LangChain Document chunks + vectors to domain VectorDocuments."""
        result = []
        for chunk, vector in zip(chunks, vectors):
            if not chunk.page_content.strip():
                continue
            metadata: Dict[str, str] = {
                k: str(v) for k, v in chunk.metadata.items()
            }
            metadata.setdefault("user_id", request.user_id)
            metadata.setdefault("filename", request.filename)
            result.append(
                VectorDocument(
                    id=None,
                    content=chunk.page_content,
                    vector=vector,
                    metadata=metadata,
                )
            )
        return result
