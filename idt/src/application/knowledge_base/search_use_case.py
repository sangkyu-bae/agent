"""KbSearchUseCase — KB 단위 하이브리드 검색 (kb-retrieval-test D1–D5).

CollectionSearchUseCase를 호출하지 않고 내부 스택(임베딩 해석→HybridSearch)만
재사용한다 — 컬렉션 권한이 아닌 KB scope 권한을 태우기 위함 (D1).
"""
from src.application.collection_search.embedding_resolver import (
    resolve_collection_embedding_model,
)
from src.application.hybrid_search.use_case import HybridSearchUseCase
from src.application.knowledge_base.content_browse_guard import KbDocumentGuard
from src.application.knowledge_base.use_case import KnowledgeBaseUseCase
from src.domain.auth.entities import User
from src.domain.collection.interfaces import ActivityLogRepositoryInterface
from src.domain.collection_search.search_history_interfaces import (
    SearchHistoryRepositoryInterface,
)
from src.domain.embedding_model.interfaces import (
    EmbeddingModelRepositoryInterface,
)
from src.domain.hybrid_search.schemas import HybridSearchRequest
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.search_schemas import (
    KbSearchRequest,
    KbSearchResult,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.embeddings.embedding_factory import EmbeddingFactory
from src.infrastructure.vector.qdrant_vectorstore import QdrantVectorStore


class KbSearchUseCase:
    def __init__(
        self,
        kb_use_case: KnowledgeBaseUseCase,
        document_guard: KbDocumentGuard,
        activity_log_repo: ActivityLogRepositoryInterface,
        embedding_model_repo: EmbeddingModelRepositoryInterface,
        embedding_factory: EmbeddingFactory,
        qdrant_client,
        es_repo,
        es_index: str,
        search_history_repo: SearchHistoryRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._kb_use_case = kb_use_case
        self._document_guard = document_guard
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
        kb_id: str,
        request: KbSearchRequest,
        user: User,
        request_id: str,
    ) -> KbSearchResult:
        self._logger.info(
            "KbSearch started",
            request_id=request_id,
            kb_id=kb_id,
            query=request.query,
            document_id=request.document_id,
        )
        # 존재 404 / KB 읽기 권한 403 (D3)
        kb = await self._kb_use_case.get(kb_id, user, request_id)
        if request.document_id:
            # KB 소속 문서 검증 — 불일치 시 ValueError not found (D4)
            await self._document_guard.ensure(
                kb_id, request.document_id, user, request_id
            )

        hybrid_result = await self._run_hybrid(kb, request, request_id)
        await self._save_history_safe(
            kb, request, user, hybrid_result, request_id
        )

        self._logger.info(
            "KbSearch completed",
            request_id=request_id,
            kb_id=kb_id,
            total_results=hybrid_result.total_found,
        )
        return KbSearchResult(
            query=hybrid_result.query,
            kb_id=kb.id,
            kb_name=kb.name,
            collection_name=kb.collection_name,
            results=hybrid_result.results,
            total_found=hybrid_result.total_found,
            bm25_weight=request.bm25_weight,
            vector_weight=request.vector_weight,
            request_id=request_id,
            document_id=request.document_id,
        )

    async def _run_hybrid(
        self, kb: KnowledgeBase, request: KbSearchRequest, request_id: str
    ):
        model = await resolve_collection_embedding_model(
            collection_name=kb.collection_name,
            activity_log_repo=self._activity_log_repo,
            embedding_model_repo=self._embedding_model_repo,
            request_id=request_id,
        )
        embedding = self._embedding_factory.create_from_string(
            provider=model.provider,
            model_name=model.model_name,
        )
        vector_store = QdrantVectorStore(
            client=self._qdrant_client,
            embedding=embedding,
            collection_name=kb.collection_name,
        )
        # D5: 컬렉션 격리 + KB 격리 (V047 이전 kb_id NULL 문서는 제외)
        metadata_filter = {
            "collection_name": kb.collection_name,
            "kb_id": kb.id,
        }
        if request.document_id:
            metadata_filter["document_id"] = request.document_id

        hybrid = HybridSearchUseCase(
            es_repo=self._es_repo,
            embedding=embedding,
            vector_store=vector_store,
            es_index=self._es_index,
            logger=self._logger,
        )
        return await hybrid.execute(
            HybridSearchRequest(
                query=request.query,
                top_k=request.top_k,
                bm25_top_k=request.bm25_top_k,
                vector_top_k=request.vector_top_k,
                rrf_k=request.rrf_k,
                metadata_filter=metadata_filter,
                bm25_weight=request.bm25_weight,
                vector_weight=request.vector_weight,
            ),
            request_id,
        )

    async def _save_history_safe(
        self,
        kb: KnowledgeBase,
        request: KbSearchRequest,
        user: User,
        hybrid_result,
        request_id: str,
    ) -> None:
        try:
            await self._search_history_repo.save(
                user_id=str(user.id),
                collection_name=kb.collection_name,
                query=request.query,
                bm25_weight=request.bm25_weight,
                vector_weight=request.vector_weight,
                top_k=request.top_k,
                result_count=hybrid_result.total_found,
                request_id=request_id,
                document_id=request.document_id,
                kb_id=kb.id,
            )
        except Exception as e:
            self._logger.warning(
                "KB search history save failed",
                exception=e,
                request_id=request_id,
            )
