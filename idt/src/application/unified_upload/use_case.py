import asyncio
import uuid

from langchain_core.documents import Document as LangchainDocument

from src.application.collection.activity_log_service import ActivityLogService
from src.application.unified_upload.schemas import (
    EsStoreResult,
    QdrantStoreResult,
    UnifiedUploadRequest,
    UnifiedUploadResult,
)
from src.domain.collection.interfaces import (
    ActivityLogRepositoryInterface,
    CollectionRepositoryInterface,
)
from src.domain.collection.schemas import ActionType
from src.domain.doc_browse.interfaces import DocumentMetadataRepositoryInterface
from src.domain.doc_browse.schemas import DocumentMetadata
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.domain.elasticsearch.schemas import ESDocument
from src.domain.embedding_model.interfaces import EmbeddingModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.morph.interfaces import MorphAnalyzerInterface
from src.domain.morph.schemas import MorphAnalysisResult
from src.domain.parser.interfaces import PDFParserInterface
from src.infrastructure.chunking.chunking_factory import ChunkingStrategyFactory
from src.infrastructure.embeddings.embedding_factory import EmbeddingFactory
from src.infrastructure.vector.qdrant_vectorstore import QdrantVectorStore
from src.domain.vector.entities import Document as VectorDocument

from qdrant_client import AsyncQdrantClient

_KEYWORD_TAGS = frozenset({"NNG", "NNP", "VV", "VA"})
_VERB_ADJ_TAGS = frozenset({"VV", "VA"})


class UnifiedUploadUseCase:
    def __init__(
        self,
        parser: PDFParserInterface,
        collection_repo: CollectionRepositoryInterface,
        activity_log_repo: ActivityLogRepositoryInterface,
        embedding_model_repo: EmbeddingModelRepositoryInterface,
        embedding_factory: EmbeddingFactory,
        qdrant_client: AsyncQdrantClient,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        morph_analyzer: MorphAnalyzerInterface,
        document_metadata_repo: DocumentMetadataRepositoryInterface,
        activity_log_service: ActivityLogService,
        logger: LoggerInterface,
    ) -> None:
        self._parser = parser
        self._collection_repo = collection_repo
        self._activity_log_repo = activity_log_repo
        self._embedding_model_repo = embedding_model_repo
        self._embedding_factory = embedding_factory
        self._qdrant_client = qdrant_client
        self._es_repo = es_repo
        self._es_index = es_index
        self._morph_analyzer = morph_analyzer
        self._document_metadata_repo = document_metadata_repo
        self._activity_log_service = activity_log_service
        self._logger = logger

    async def execute(
        self, request: UnifiedUploadRequest, request_id: str
    ) -> UnifiedUploadResult:
        self._logger.info(
            "UnifiedUpload started",
            request_id=request_id,
            filename=request.filename,
            collection=request.collection_name,
        )

        if not await self._collection_repo.collection_exists(request.collection_name):
            raise ValueError(f"Collection '{request.collection_name}' not found")

        embedding_model = await self._resolve_embedding_model(
            request.collection_name, request_id
        )

        parsed_docs = self._parser.parse_bytes(
            request.file_bytes, request.filename, request.user_id
        )
        total_pages = len(parsed_docs)

        strategy = ChunkingStrategyFactory.create_strategy(
            "parent_child",
            parent_chunk_size=2000,
            child_chunk_size=request.child_chunk_size,
            child_chunk_overlap=request.child_chunk_overlap,
        )
        chunks = strategy.chunk(parsed_docs)

        document_id = str(uuid.uuid4())
        for chunk in chunks:
            chunk.metadata["document_id"] = document_id
            chunk.metadata["user_id"] = request.user_id
            chunk.metadata["collection_name"] = request.collection_name

        qdrant_raw, es_raw = await asyncio.gather(
            self._store_to_qdrant(
                chunks, embedding_model, request, request_id
            ),
            self._store_to_es(
                chunks, document_id, request, request_id
            ),
            return_exceptions=True,
        )

        if isinstance(qdrant_raw, Exception):
            self._logger.error(
                "Qdrant store failed",
                exception=qdrant_raw,
                request_id=request_id,
                collection_name=request.collection_name,
            )
        if isinstance(es_raw, Exception):
            self._logger.error(
                "ES store failed",
                exception=es_raw,
                request_id=request_id,
                document_id=document_id,
                collection_name=request.collection_name,
            )

        qdrant_result = self._to_qdrant_result(qdrant_raw, embedding_model.model_name)
        es_result = self._to_es_result(es_raw)

        status = self._determine_status(qdrant_result, es_result)

        try:
            await self._document_metadata_repo.save(
                DocumentMetadata(
                    document_id=document_id,
                    collection_name=request.collection_name,
                    filename=request.filename,
                    category="uncategorized",
                    user_id=request.user_id,
                    chunk_count=len(chunks),
                    chunk_strategy="parent_child",
                ),
                request_id=request_id,
            )
        except Exception:
            self._logger.warning(
                "Document metadata save failed, continuing",
                request_id=request_id,
                document_id=document_id,
            )

        await self._activity_log_service.log(
            collection_name=request.collection_name,
            action=ActionType.ADD_DOCUMENT,
            request_id=request_id,
            user_id=request.user_id,
            detail={
                "document_id": document_id,
                "filename": request.filename,
                "total_pages": total_pages,
                "chunk_count": len(chunks),
                "embedding_model": embedding_model.model_name,
                "qdrant_status": "success" if not qdrant_result.error else "failed",
                "es_status": "success" if not es_result.error else "failed",
                "status": status,
            },
        )

        self._logger.info(
            "UnifiedUpload completed",
            request_id=request_id,
            document_id=document_id,
            status=status,
            chunk_count=len(chunks),
        )

        return UnifiedUploadResult(
            document_id=document_id,
            filename=request.filename,
            total_pages=total_pages,
            chunk_count=len(chunks),
            collection_name=request.collection_name,
            qdrant=qdrant_result,
            es=es_result,
            chunking_config={
                "strategy": "parent_child",
                "parent_chunk_size": 2000,
                "child_chunk_size": request.child_chunk_size,
                "child_chunk_overlap": request.child_chunk_overlap,
            },
            status=status,
        )

    async def _resolve_embedding_model(self, collection_name: str, request_id: str):
        logs = await self._activity_log_repo.find_all(
            request_id=request_id,
            collection_name=collection_name,
            action="CREATE",
            limit=1,
        )
        if not logs or not logs[0].detail:
            raise ValueError(
                f"Cannot determine embedding model for collection '{collection_name}'"
            )

        model_name = logs[0].detail.get("embedding_model")
        if not model_name:
            raise ValueError(
                f"Cannot determine embedding model for collection '{collection_name}'"
            )

        model = await self._embedding_model_repo.find_by_model_name(
            model_name, request_id
        )
        if model is None:
            raise ValueError(f"Embedding model '{model_name}' not registered")

        return model

    async def _store_to_qdrant(
        self, chunks, embedding_model, request, request_id
    ) -> QdrantStoreResult:
        embedding = self._embedding_factory.create_from_string(
            provider=embedding_model.provider,
            model_name=embedding_model.model_name,
        )
        texts = [chunk.page_content for chunk in chunks]
        vectors = await embedding.embed_documents(texts)

        vectorstore = QdrantVectorStore(
            client=self._qdrant_client,
            embedding=embedding,
            collection_name=request.collection_name,
        )
        documents = [
            VectorDocument(
                id=None,
                content=text,
                vector=vector,
                metadata={k: str(v) for k, v in chunk.metadata.items()},
            )
            for text, vector, chunk in zip(texts, vectors, chunks)
        ]
        stored_ids = await vectorstore.add_documents(documents)
        return QdrantStoreResult(
            stored_ids=[sid.value for sid in stored_ids],
            embedding_model=embedding_model.model_name,
        )

    async def _store_to_es(
        self, chunks, document_id, request, request_id
    ) -> EsStoreResult:
        es_docs = []
        for chunk in chunks:
            morph_result = self._morph_analyzer.analyze(chunk.page_content)
            morph_keywords = self._extract_morph_keywords(morph_result)
            morph_text = " ".join(morph_keywords)

            chunk_id = chunk.metadata.get("chunk_id", str(uuid.uuid4()))
            body = {
                "content": chunk.page_content,
                "morph_keywords": morph_keywords,
                "morph_text": morph_text,
                "chunk_id": chunk_id,
                "chunk_type": chunk.metadata.get("chunk_type", "full"),
                "chunk_index": chunk.metadata.get("chunk_index", 0),
                "total_chunks": chunk.metadata.get("total_chunks", 1),
                "document_id": document_id,
                "user_id": request.user_id,
                "collection_name": request.collection_name,
            }
            if "parent_id" in chunk.metadata:
                body["parent_id"] = chunk.metadata["parent_id"]
            es_docs.append(ESDocument(id=chunk_id, body=body, index=self._es_index))

        count = await self._es_repo.bulk_index(es_docs, request_id)
        return EsStoreResult(indexed_count=count)

    def _extract_morph_keywords(self, analysis: MorphAnalysisResult) -> list[str]:
        seen: set[str] = set()
        keywords: list[str] = []
        for tok in analysis.tokens:
            if tok.pos not in _KEYWORD_TAGS:
                continue
            form = tok.surface + "다" if tok.pos in _VERB_ADJ_TAGS else tok.surface
            if form not in seen:
                seen.add(form)
                keywords.append(form)
        return keywords

    @staticmethod
    def _to_qdrant_result(raw, model_name: str) -> QdrantStoreResult:
        if isinstance(raw, QdrantStoreResult):
            return raw
        return QdrantStoreResult(
            stored_ids=[], embedding_model=model_name, error=str(raw)
        )

    @staticmethod
    def _to_es_result(raw) -> EsStoreResult:
        if isinstance(raw, EsStoreResult):
            return raw
        return EsStoreResult(indexed_count=0, error=str(raw))

    @staticmethod
    def _determine_status(
        qdrant: QdrantStoreResult, es: EsStoreResult
    ) -> str:
        if qdrant.error and es.error:
            return "failed"
        if qdrant.error or es.error:
            return "partial"
        return "completed"
