import uuid
from dataclasses import dataclass
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.application.unified_upload.schemas import (
    UnifiedUploadRequest,
)
from src.application.unified_upload.use_case import UnifiedUploadUseCase
from src.domain.collection.schemas import ActionType, ActivityLogEntry
from src.domain.embedding_model.entity import EmbeddingModel
from src.domain.morph.schemas import MorphAnalysisResult, MorphToken


def _make_request(**overrides) -> UnifiedUploadRequest:
    defaults = dict(
        file_bytes=b"%PDF-1.4 fake",
        filename="test.pdf",
        user_id="user-1",
        collection_name="my-collection",
        child_chunk_size=500,
        child_chunk_overlap=50,
    )
    defaults.update(overrides)
    return UnifiedUploadRequest(**defaults)


def _make_embedding_model() -> EmbeddingModel:
    return EmbeddingModel(
        id=1,
        provider="openai",
        model_name="text-embedding-3-small",
        display_name="OpenAI Small",
        vector_dimension=1536,
        is_active=True,
        description=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _make_activity_log_entry(embedding_model: str = "text-embedding-3-small"):
    return ActivityLogEntry(
        id=1,
        collection_name="my-collection",
        action=ActionType.CREATE,
        user_id="admin",
        detail={"embedding_model": embedding_model},
        created_at=datetime.now(),
    )


def _fake_chunk(content: str = "chunk text", metadata: dict | None = None):
    chunk = MagicMock()
    chunk.page_content = content
    chunk.metadata = metadata or {
        "chunk_id": str(uuid.uuid4()),
        "chunk_type": "child",
        "chunk_index": 0,
        "total_chunks": 1,
    }
    return chunk


def _make_morph_result(text: str = "chunk text") -> MorphAnalysisResult:
    return MorphAnalysisResult(
        tokens=(
            MorphToken(surface="한국은행", pos="NNP", start=0, length=4),
            MorphToken(surface="기준금리", pos="NNG", start=5, length=4),
            MorphToken(surface="동결하", pos="VV", start=10, length=3),
        ),
        text=text,
    )


def _build_use_case(**overrides):
    defaults = dict(
        parser=MagicMock(),
        collection_repo=AsyncMock(),
        activity_log_repo=AsyncMock(),
        embedding_model_repo=AsyncMock(),
        embedding_factory=MagicMock(),
        qdrant_client=AsyncMock(),
        es_repo=AsyncMock(),
        es_index="test-index",
        morph_analyzer=MagicMock(),
        document_metadata_repo=AsyncMock(),
        activity_log_service=AsyncMock(),
        logger=MagicMock(),
    )
    defaults.update(overrides)
    return UnifiedUploadUseCase(**defaults), defaults


class TestUnifiedUploadUseCase:
    @pytest.mark.asyncio
    async def test_execute_success_both_stores(self):
        uc, deps = _build_use_case()
        request = _make_request()
        model = _make_embedding_model()

        deps["collection_repo"].collection_exists.return_value = True
        deps["activity_log_repo"].find_all.return_value = [_make_activity_log_entry()]
        deps["embedding_model_repo"].find_by_model_name.return_value = model

        fake_chunks = [_fake_chunk("text 1"), _fake_chunk("text 2")]
        deps["parser"].parse_bytes.return_value = [MagicMock(), MagicMock()]

        mock_embedding = AsyncMock()
        mock_embedding.embed_documents.return_value = [[0.1] * 1536, [0.2] * 1536]
        deps["embedding_factory"].create_from_string.return_value = mock_embedding

        deps["morph_analyzer"].analyze.return_value = _make_morph_result()
        deps["es_repo"].bulk_index.return_value = 2

        with patch(
            "src.application.unified_upload.use_case.ChunkingStrategyFactory"
        ) as mock_factory, patch(
            "src.application.unified_upload.use_case.QdrantVectorStore"
        ) as mock_vs_cls:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = fake_chunks
            mock_factory.create_strategy.return_value = mock_strategy

            mock_vs = AsyncMock()
            mock_doc_id = MagicMock()
            mock_doc_id.value = "stored-id-1"
            mock_vs.add_documents.return_value = [mock_doc_id, mock_doc_id]
            mock_vs_cls.return_value = mock_vs

            result = await uc.execute(request, "req-1")

        assert result.status == "completed"
        assert result.filename == "test.pdf"
        assert result.chunk_count == 2
        assert result.total_pages == 2
        assert result.qdrant.error is None
        assert result.es.error is None
        assert result.es.indexed_count == 2
        assert result.chunking_config["strategy"] == "parent_child"

    @pytest.mark.asyncio
    async def test_execute_collection_not_found_raises(self):
        uc, deps = _build_use_case()
        deps["collection_repo"].collection_exists.return_value = False

        with pytest.raises(ValueError, match="not found"):
            await uc.execute(_make_request(), "req-1")

    @pytest.mark.asyncio
    async def test_execute_no_create_log_raises(self):
        uc, deps = _build_use_case()
        deps["collection_repo"].collection_exists.return_value = True
        deps["activity_log_repo"].find_all.return_value = []

        with pytest.raises(ValueError, match="Cannot determine embedding model"):
            await uc.execute(_make_request(), "req-1")

    @pytest.mark.asyncio
    async def test_execute_embedding_model_not_registered_raises(self):
        uc, deps = _build_use_case()
        deps["collection_repo"].collection_exists.return_value = True
        deps["activity_log_repo"].find_all.return_value = [_make_activity_log_entry()]
        deps["embedding_model_repo"].find_by_model_name.return_value = None

        with pytest.raises(ValueError, match="not registered"):
            await uc.execute(_make_request(), "req-1")

    @pytest.mark.asyncio
    async def test_execute_qdrant_fails_returns_partial(self):
        uc, deps = _build_use_case()
        request = _make_request()
        model = _make_embedding_model()

        deps["collection_repo"].collection_exists.return_value = True
        deps["activity_log_repo"].find_all.return_value = [_make_activity_log_entry()]
        deps["embedding_model_repo"].find_by_model_name.return_value = model
        deps["parser"].parse_bytes.return_value = [MagicMock()]

        mock_embedding = AsyncMock()
        mock_embedding.embed_documents.side_effect = RuntimeError("Qdrant down")
        deps["embedding_factory"].create_from_string.return_value = mock_embedding

        deps["morph_analyzer"].analyze.return_value = _make_morph_result()
        deps["es_repo"].bulk_index.return_value = 1

        with patch(
            "src.application.unified_upload.use_case.ChunkingStrategyFactory"
        ) as mock_factory:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = [_fake_chunk()]
            mock_factory.create_strategy.return_value = mock_strategy

            result = await uc.execute(request, "req-1")

        assert result.status == "partial"
        assert result.qdrant.error is not None
        assert result.es.error is None

    @pytest.mark.asyncio
    async def test_execute_es_fails_returns_partial(self):
        uc, deps = _build_use_case()
        request = _make_request()
        model = _make_embedding_model()

        deps["collection_repo"].collection_exists.return_value = True
        deps["activity_log_repo"].find_all.return_value = [_make_activity_log_entry()]
        deps["embedding_model_repo"].find_by_model_name.return_value = model
        deps["parser"].parse_bytes.return_value = [MagicMock()]

        mock_embedding = AsyncMock()
        mock_embedding.embed_documents.return_value = [[0.1] * 1536]
        deps["embedding_factory"].create_from_string.return_value = mock_embedding

        deps["morph_analyzer"].analyze.side_effect = RuntimeError("ES down")

        with patch(
            "src.application.unified_upload.use_case.ChunkingStrategyFactory"
        ) as mock_factory, patch(
            "src.application.unified_upload.use_case.QdrantVectorStore"
        ) as mock_vs_cls:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = [_fake_chunk()]
            mock_factory.create_strategy.return_value = mock_strategy

            mock_vs = AsyncMock()
            mock_doc_id = MagicMock()
            mock_doc_id.value = "stored-id-1"
            mock_vs.add_documents.return_value = [mock_doc_id]
            mock_vs_cls.return_value = mock_vs

            result = await uc.execute(request, "req-1")

        assert result.status == "partial"
        assert result.qdrant.error is None
        assert result.es.error is not None

    @pytest.mark.asyncio
    async def test_execute_both_fail_returns_failed(self):
        uc, deps = _build_use_case()
        request = _make_request()
        model = _make_embedding_model()

        deps["collection_repo"].collection_exists.return_value = True
        deps["activity_log_repo"].find_all.return_value = [_make_activity_log_entry()]
        deps["embedding_model_repo"].find_by_model_name.return_value = model
        deps["parser"].parse_bytes.return_value = [MagicMock()]

        mock_embedding = AsyncMock()
        mock_embedding.embed_documents.side_effect = RuntimeError("Qdrant down")
        deps["embedding_factory"].create_from_string.return_value = mock_embedding

        deps["morph_analyzer"].analyze.side_effect = RuntimeError("ES down")

        with patch(
            "src.application.unified_upload.use_case.ChunkingStrategyFactory"
        ) as mock_factory:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = [_fake_chunk()]
            mock_factory.create_strategy.return_value = mock_strategy

            result = await uc.execute(request, "req-1")

        assert result.status == "failed"
        assert result.qdrant.error is not None
        assert result.es.error is not None

    @pytest.mark.asyncio
    async def test_execute_custom_chunk_params(self):
        uc, deps = _build_use_case()
        request = _make_request(child_chunk_size=1000, child_chunk_overlap=100)
        model = _make_embedding_model()

        deps["collection_repo"].collection_exists.return_value = True
        deps["activity_log_repo"].find_all.return_value = [_make_activity_log_entry()]
        deps["embedding_model_repo"].find_by_model_name.return_value = model
        deps["parser"].parse_bytes.return_value = [MagicMock()]

        mock_embedding = AsyncMock()
        mock_embedding.embed_documents.return_value = [[0.1] * 1536]
        deps["embedding_factory"].create_from_string.return_value = mock_embedding
        deps["morph_analyzer"].analyze.return_value = _make_morph_result()
        deps["es_repo"].bulk_index.return_value = 1

        with patch(
            "src.application.unified_upload.use_case.ChunkingStrategyFactory"
        ) as mock_factory, patch(
            "src.application.unified_upload.use_case.QdrantVectorStore"
        ) as mock_vs_cls:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = [_fake_chunk()]
            mock_factory.create_strategy.return_value = mock_strategy

            mock_vs = AsyncMock()
            mock_doc_id = MagicMock()
            mock_doc_id.value = "id-1"
            mock_vs.add_documents.return_value = [mock_doc_id]
            mock_vs_cls.return_value = mock_vs

            result = await uc.execute(request, "req-1")

        mock_factory.create_strategy.assert_called_once_with(
            "parent_child",
            parent_chunk_size=2000,
            child_chunk_size=1000,
            child_chunk_overlap=100,
        )
        assert result.chunking_config["child_chunk_size"] == 1000
        assert result.chunking_config["child_chunk_overlap"] == 100

    @pytest.mark.asyncio
    async def test_execute_saves_document_metadata(self):
        uc, deps = _build_use_case()
        request = _make_request()
        model = _make_embedding_model()

        deps["collection_repo"].collection_exists.return_value = True
        deps["activity_log_repo"].find_all.return_value = [_make_activity_log_entry()]
        deps["embedding_model_repo"].find_by_model_name.return_value = model

        fake_chunks = [_fake_chunk("text 1"), _fake_chunk("text 2")]
        deps["parser"].parse_bytes.return_value = [MagicMock()]

        mock_embedding = AsyncMock()
        mock_embedding.embed_documents.return_value = [[0.1] * 1536, [0.2] * 1536]
        deps["embedding_factory"].create_from_string.return_value = mock_embedding

        deps["morph_analyzer"].analyze.return_value = _make_morph_result()
        deps["es_repo"].bulk_index.return_value = 2

        with patch(
            "src.application.unified_upload.use_case.ChunkingStrategyFactory"
        ) as mock_factory, patch(
            "src.application.unified_upload.use_case.QdrantVectorStore"
        ) as mock_vs_cls:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = fake_chunks
            mock_factory.create_strategy.return_value = mock_strategy

            mock_vs = AsyncMock()
            mock_doc_id = MagicMock()
            mock_doc_id.value = "stored-id-1"
            mock_vs.add_documents.return_value = [mock_doc_id, mock_doc_id]
            mock_vs_cls.return_value = mock_vs

            result = await uc.execute(request, "req-1")

        deps["document_metadata_repo"].save.assert_called_once()
        saved_metadata = deps["document_metadata_repo"].save.call_args[0][0]
        assert saved_metadata.collection_name == "my-collection"
        assert saved_metadata.filename == "test.pdf"
        assert saved_metadata.user_id == "user-1"
        assert saved_metadata.chunk_count == 2
        assert saved_metadata.chunk_strategy == "parent_child"

    @pytest.mark.asyncio
    async def test_execute_metadata_save_failure_does_not_fail(self):
        uc, deps = _build_use_case()
        request = _make_request()
        model = _make_embedding_model()

        deps["collection_repo"].collection_exists.return_value = True
        deps["activity_log_repo"].find_all.return_value = [_make_activity_log_entry()]
        deps["embedding_model_repo"].find_by_model_name.return_value = model
        deps["parser"].parse_bytes.return_value = [MagicMock()]

        mock_embedding = AsyncMock()
        mock_embedding.embed_documents.return_value = [[0.1] * 1536]
        deps["embedding_factory"].create_from_string.return_value = mock_embedding

        deps["morph_analyzer"].analyze.return_value = _make_morph_result()
        deps["es_repo"].bulk_index.return_value = 1
        deps["document_metadata_repo"].save.side_effect = RuntimeError("DB down")

        with patch(
            "src.application.unified_upload.use_case.ChunkingStrategyFactory"
        ) as mock_factory, patch(
            "src.application.unified_upload.use_case.QdrantVectorStore"
        ) as mock_vs_cls:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = [_fake_chunk()]
            mock_factory.create_strategy.return_value = mock_strategy

            mock_vs = AsyncMock()
            mock_doc_id = MagicMock()
            mock_doc_id.value = "stored-id-1"
            mock_vs.add_documents.return_value = [mock_doc_id]
            mock_vs_cls.return_value = mock_vs

            result = await uc.execute(request, "req-1")

        assert result.status == "completed"
        deps["logger"].warning.assert_called()

    @pytest.mark.asyncio
    async def test_store_to_es_uses_morph_keywords_and_morph_text(self):
        uc, deps = _build_use_case()
        request = _make_request()
        model = _make_embedding_model()

        deps["collection_repo"].collection_exists.return_value = True
        deps["activity_log_repo"].find_all.return_value = [_make_activity_log_entry()]
        deps["embedding_model_repo"].find_by_model_name.return_value = model
        deps["parser"].parse_bytes.return_value = [MagicMock()]

        mock_embedding = AsyncMock()
        mock_embedding.embed_documents.return_value = [[0.1] * 1536]
        deps["embedding_factory"].create_from_string.return_value = mock_embedding

        deps["morph_analyzer"].analyze.return_value = _make_morph_result()
        deps["es_repo"].bulk_index.return_value = 1

        with patch(
            "src.application.unified_upload.use_case.ChunkingStrategyFactory"
        ) as mock_factory, patch(
            "src.application.unified_upload.use_case.QdrantVectorStore"
        ) as mock_vs_cls:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = [_fake_chunk()]
            mock_factory.create_strategy.return_value = mock_strategy

            mock_vs = AsyncMock()
            mock_doc_id = MagicMock()
            mock_doc_id.value = "stored-id-1"
            mock_vs.add_documents.return_value = [mock_doc_id]
            mock_vs_cls.return_value = mock_vs

            await uc.execute(request, "req-1")

        es_docs = deps["es_repo"].bulk_index.call_args[0][0]
        body = es_docs[0].body
        assert "morph_keywords" in body
        assert "morph_text" in body
        assert "keywords" not in body
        assert isinstance(body["morph_keywords"], list)
        assert isinstance(body["morph_text"], str)
        assert body["morph_keywords"] == ["한국은행", "기준금리", "동결하다"]
        assert body["morph_text"] == "한국은행 기준금리 동결하다"

    @pytest.mark.asyncio
    async def test_execute_es_fails_logs_error(self):
        """ES 저장 실패 시 logger.error가 호출된다."""
        uc, deps = _build_use_case()
        request = _make_request()
        model = _make_embedding_model()

        deps["collection_repo"].collection_exists.return_value = True
        deps["activity_log_repo"].find_all.return_value = [_make_activity_log_entry()]
        deps["embedding_model_repo"].find_by_model_name.return_value = model
        deps["parser"].parse_bytes.return_value = [MagicMock()]

        mock_embedding = AsyncMock()
        mock_embedding.embed_documents.return_value = [[0.1] * 1536]
        deps["embedding_factory"].create_from_string.return_value = mock_embedding

        deps["morph_analyzer"].analyze.side_effect = RuntimeError("morph fail")

        with patch(
            "src.application.unified_upload.use_case.ChunkingStrategyFactory"
        ) as mock_factory, patch(
            "src.application.unified_upload.use_case.QdrantVectorStore"
        ) as mock_vs_cls:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = [_fake_chunk()]
            mock_factory.create_strategy.return_value = mock_strategy

            mock_vs = AsyncMock()
            mock_doc_id = MagicMock()
            mock_doc_id.value = "stored-id-1"
            mock_vs.add_documents.return_value = [mock_doc_id]
            mock_vs_cls.return_value = mock_vs

            result = await uc.execute(request, "req-1")

        assert result.es.error is not None
        error_calls = [
            c for c in deps["logger"].error.call_args_list
            if "ES" in str(c)
        ]
        assert len(error_calls) >= 1

    @pytest.mark.asyncio
    async def test_execute_qdrant_fails_logs_error(self):
        """Qdrant 저장 실패 시 logger.error가 호출된다."""
        uc, deps = _build_use_case()
        request = _make_request()
        model = _make_embedding_model()

        deps["collection_repo"].collection_exists.return_value = True
        deps["activity_log_repo"].find_all.return_value = [_make_activity_log_entry()]
        deps["embedding_model_repo"].find_by_model_name.return_value = model
        deps["parser"].parse_bytes.return_value = [MagicMock()]

        mock_embedding = AsyncMock()
        mock_embedding.embed_documents.side_effect = RuntimeError("Qdrant down")
        deps["embedding_factory"].create_from_string.return_value = mock_embedding

        deps["morph_analyzer"].analyze.return_value = _make_morph_result()
        deps["es_repo"].bulk_index.return_value = 1

        with patch(
            "src.application.unified_upload.use_case.ChunkingStrategyFactory"
        ) as mock_factory:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = [_fake_chunk()]
            mock_factory.create_strategy.return_value = mock_strategy

            result = await uc.execute(request, "req-1")

        assert result.qdrant.error is not None
        error_calls = [
            c for c in deps["logger"].error.call_args_list
            if "Qdrant" in str(c)
        ]
        assert len(error_calls) >= 1
