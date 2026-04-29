from src.application.collection.permission_service import CollectionPermissionService
from src.application.hybrid_search.use_case import HybridSearchUseCase
from src.domain.auth.entities import User
from src.domain.collection.interfaces import (
    ActivityLogRepositoryInterface,
    CollectionRepositoryInterface,
)
from src.domain.collection_search.schemas import (
    CollectionSearchRequest,
    CollectionSearchResponse,
)
from src.domain.collection_search.search_history_interfaces import (
    SearchHistoryRepositoryInterface,
)
from src.domain.embedding_model.interfaces import EmbeddingModelRepositoryInterface
from src.domain.hybrid_search.schemas import HybridSearchRequest
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.embeddings.embedding_factory import EmbeddingFactory
from src.infrastructure.vector.qdrant_vectorstore import QdrantVectorStore


class CollectionNotFoundError(Exception):
    def __init__(self, collection_name: str) -> None:
        self.collection_name = collection_name
        super().__init__(f"Collection '{collection_name}' not found")


class CollectionSearchUseCase:
    def __init__(
        self,
        collection_repo: CollectionRepositoryInterface,
        permission_service: CollectionPermissionService,
        activity_log_repo: ActivityLogRepositoryInterface,
        embedding_model_repo: EmbeddingModelRepositoryInterface,
        embedding_factory: EmbeddingFactory,
        qdrant_client,
        es_repo,
        es_index: str,
        search_history_repo: SearchHistoryRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._collection_repo = collection_repo
        self._permission_service = permission_service
        self._activity_log_repo = activity_log_repo
        self._embedding_model_repo = embedding_model_repo
        self._embedding_factory = embedding_factory
        self._qdrant_client = qdrant_client
        self._es_repo = es_repo
        self._es_index = es_index
        self._search_history_repo = search_history_repo
        self._logger = logger

    async def execute(
        self,
        request: CollectionSearchRequest,
        user: User,
        request_id: str,
    ) -> CollectionSearchResponse:
        self._logger.info(
            "CollectionSearch started",
            request_id=request_id,
            collection=request.collection_name,
            query=request.query,
        )

        await self._permission_service.check_read_access(
            request.collection_name, user, request_id
        )

        if not await self._collection_repo.collection_exists(
            request.collection_name
        ):
            raise CollectionNotFoundError(request.collection_name)

        embedding_model = await self._resolve_embedding_model(
            request.collection_name, request_id
        )

        embedding = self._embedding_factory.create_from_string(
            provider=embedding_model.provider,
            model_name=embedding_model.model_name,
        )
        vector_store = QdrantVectorStore(
            client=self._qdrant_client,
            embedding=embedding,
            collection_name=request.collection_name,
        )

        metadata_filter = {"collection_name": request.collection_name}
        if request.document_id:
            metadata_filter["document_id"] = request.document_id

        hybrid_use_case = HybridSearchUseCase(
            es_repo=self._es_repo,
            embedding=embedding,
            vector_store=vector_store,
            es_index=self._es_index,
            logger=self._logger,
        )
        hybrid_request = HybridSearchRequest(
            query=request.query,
            top_k=request.top_k,
            bm25_top_k=request.bm25_top_k,
            vector_top_k=request.vector_top_k,
            rrf_k=request.rrf_k,
            metadata_filter=metadata_filter,
            bm25_weight=request.bm25_weight,
            vector_weight=request.vector_weight,
        )
        hybrid_result = await hybrid_use_case.execute(hybrid_request, request_id)

        await self._save_history_safe(request, user, hybrid_result, request_id)

        self._logger.info(
            "CollectionSearch completed",
            request_id=request_id,
            total_results=hybrid_result.total_found,
        )

        return CollectionSearchResponse(
            query=hybrid_result.query,
            collection_name=request.collection_name,
            results=hybrid_result.results,
            total_found=hybrid_result.total_found,
            bm25_weight=request.bm25_weight,
            vector_weight=request.vector_weight,
            request_id=request_id,
            document_id=request.document_id,
        )

    async def _resolve_embedding_model(
        self, collection_name: str, request_id: str
    ):
        logs = await self._activity_log_repo.find_all(
            request_id=request_id,
            collection_name=collection_name,
            action="CREATE",
            limit=1,
        )
        if not logs or not logs[0].detail:
            raise ValueError(
                f"Cannot determine embedding model for '{collection_name}'"
            )
        model_name = logs[0].detail.get("embedding_model")
        if not model_name:
            raise ValueError(
                f"Cannot determine embedding model for '{collection_name}'"
            )
        model = await self._embedding_model_repo.find_by_model_name(
            model_name, request_id
        )
        if model is None:
            raise ValueError(f"Embedding model '{model_name}' not registered")
        return model

    async def _save_history_safe(
        self, request, user, hybrid_result, request_id
    ) -> None:
        try:
            await self._search_history_repo.save(
                user_id=str(user.id),
                collection_name=request.collection_name,
                query=request.query,
                bm25_weight=request.bm25_weight,
                vector_weight=request.vector_weight,
                top_k=request.top_k,
                result_count=hybrid_result.total_found,
                request_id=request_id,
                document_id=request.document_id,
            )
        except Exception as e:
            self._logger.warning(
                "Search history save failed",
                exception=e,
                request_id=request_id,
            )
