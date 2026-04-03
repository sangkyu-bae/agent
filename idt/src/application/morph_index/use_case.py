"""MorphAndDualIndexUseCase: Kiwi 형태소 분석 + Qdrant + ES 이중 색인 오케스트레이션."""
import json
import uuid

from langchain_core.documents import Document as LCDoc

from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.domain.elasticsearch.schemas import ESDocument
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.morph.interfaces import MorphAnalyzerInterface
from src.domain.morph.schemas import MorphAnalysisResult
from src.domain.morph_index.schemas import (
    DualIndexedChunk,
    MorphIndexRequest,
    MorphIndexResult,
)
from src.domain.vector.entities import Document as VecDoc
from src.domain.vector.interfaces import EmbeddingInterface, VectorStoreInterface
from src.domain.vector.value_objects import DocumentId

_KEYWORD_TAGS = frozenset({"NNG", "NNP", "VV", "VA"})
_VERB_ADJ_TAGS = frozenset({"VV", "VA"})


class MorphAndDualIndexUseCase:
    """문서를 청킹하고 Kiwi 형태소 분석 후 Qdrant + ES에 이중 색인한다."""

    def __init__(
        self,
        chunking_strategy: ChunkingStrategy,
        morph_analyzer: MorphAnalyzerInterface,
        embedding: EmbeddingInterface,
        vector_store: VectorStoreInterface,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        logger: LoggerInterface,
    ) -> None:
        self._chunking_strategy = chunking_strategy
        self._morph_analyzer = morph_analyzer
        self._embedding = embedding
        self._vector_store = vector_store
        self._es_repo = es_repo
        self._es_index = es_index
        self._logger = logger

    async def execute(
        self, request: MorphIndexRequest, request_id: str
    ) -> MorphIndexResult:
        """청킹 → 형태소 분석 → 임베딩 → Qdrant + ES 색인.

        Args:
            request: 이중 색인 요청 파라미터
            request_id: 요청 추적 ID

        Returns:
            이중 색인 결과 (Qdrant + ES 통계 포함)
        """
        self._logger.info(
            "MorphDualIndex started",
            request_id=request_id,
            document_id=request.document_id,
            strategy_type=request.strategy_type,
        )
        try:
            # 1. 청킹
            lc_doc = LCDoc(
                page_content=request.content,
                metadata={
                    "document_id": request.document_id,
                    "user_id": request.user_id,
                    **request.metadata,
                },
            )
            chunks = self._chunking_strategy.chunk([lc_doc])

            # 2. 형태소 분석 + 위치 계산
            morph_results = [
                self._morph_analyzer.analyze(c.page_content) for c in chunks
            ]
            char_ranges = [
                self._find_char_range(request.content, c.page_content)
                for c in chunks
            ]

            # 3. 임베딩 (배치)
            texts = [c.page_content for c in chunks]
            vectors = await self._embedding.embed_documents(texts)

            # 4. Qdrant Document 빌드 + 색인
            vec_docs = [
                self._build_vec_doc(
                    chunk=chunks[i],
                    vector=vectors[i],
                    morph_keywords=self._extract_morph_keywords(morph_results[i]),
                    char_start=char_ranges[i][0],
                    char_end=char_ranges[i][1],
                    document_id=request.document_id,
                    user_id=request.user_id,
                    source=request.source,
                )
                for i in range(len(chunks))
            ]
            await self._vector_store.add_documents(vec_docs)

            # 5. ES Document 빌드 + 색인
            indexed_chunks: list[DualIndexedChunk] = []
            es_docs: list[ESDocument] = []

            for i, chunk in enumerate(chunks):
                keywords = self._extract_morph_keywords(morph_results[i])
                char_start, char_end = char_ranges[i]
                chunk_id = chunk.metadata.get("chunk_id") or str(uuid.uuid4())
                chunk_type = chunk.metadata.get("chunk_type", "full")
                chunk_index = chunk.metadata.get("chunk_index", i)

                body: dict = {
                    "content": chunk.page_content,
                    "morph_keywords": keywords,
                    "chunk_id": chunk_id,
                    "chunk_type": chunk_type,
                    "chunk_index": chunk_index,
                    "total_chunks": chunk.metadata.get("total_chunks", len(chunks)),
                    "char_start": char_start,
                    "char_end": char_end,
                    "document_id": request.document_id,
                    "user_id": request.user_id,
                }
                if request.source:
                    body["source"] = request.source
                if "parent_id" in chunk.metadata:
                    body["parent_id"] = chunk.metadata["parent_id"]

                es_docs.append(ESDocument(id=chunk_id, body=body, index=self._es_index))
                indexed_chunks.append(
                    DualIndexedChunk(
                        chunk_id=chunk_id,
                        chunk_type=chunk_type,
                        morph_keywords=keywords,
                        content=chunk.page_content,
                        char_start=char_start,
                        char_end=char_end,
                        chunk_index=chunk_index,
                    )
                )

            await self._es_repo.bulk_index(es_docs, request_id)

            self._logger.info(
                "MorphDualIndex completed",
                request_id=request_id,
                document_id=request.document_id,
                total_chunks=len(indexed_chunks),
            )
            return MorphIndexResult(
                document_id=request.document_id,
                user_id=request.user_id,
                total_chunks=len(indexed_chunks),
                qdrant_indexed=len(vec_docs),
                es_indexed=len(es_docs),
                indexed_chunks=indexed_chunks,
                request_id=request_id,
            )
        except Exception as e:
            self._logger.error(
                "MorphDualIndex failed",
                exception=e,
                request_id=request_id,
                document_id=request.document_id,
            )
            raise

    # ──────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────

    def _extract_morph_keywords(self, analysis: MorphAnalysisResult) -> list[str]:
        """NNG + NNP 그대로, VV/VA는 원형(기본형 = 어간 + 다) 반환."""
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

    def _find_char_range(self, original: str, content: str) -> tuple[int, int]:
        """청크 내용의 원본 문서 내 문자 위치 범위를 반환한다."""
        idx = original.find(content)
        if idx == -1:
            return 0, len(content)
        return idx, idx + len(content)

    def _build_vec_doc(
        self,
        chunk: LCDoc,
        vector: list[float],
        morph_keywords: list[str],
        char_start: int,
        char_end: int,
        document_id: str,
        user_id: str,
        source: str,
    ) -> VecDoc:
        """Qdrant 저장용 도메인 Document를 생성한다."""
        chunk_id = chunk.metadata.get("chunk_id") or str(uuid.uuid4())
        chunk_type = chunk.metadata.get("chunk_type", "full")
        chunk_index = str(chunk.metadata.get("chunk_index", 0))

        metadata: dict[str, str] = {
            "document_id": document_id,
            "user_id": user_id,
            "chunk_id": chunk_id,
            "chunk_type": chunk_type,
            "chunk_index": chunk_index,
            "total_chunks": str(chunk.metadata.get("total_chunks", 1)),
            "char_start": str(char_start),
            "char_end": str(char_end),
            "morph_keywords": json.dumps(morph_keywords, ensure_ascii=False),
        }
        if source:
            metadata["source"] = source
        if "parent_id" in chunk.metadata:
            metadata["parent_id"] = str(chunk.metadata["parent_id"])

        return VecDoc(
            id=DocumentId(chunk_id),
            content=chunk.page_content,
            vector=vector,
            metadata=metadata,
        )
