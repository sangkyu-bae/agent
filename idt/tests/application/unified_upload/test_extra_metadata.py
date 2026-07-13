"""extra_metadata additive 필드 검증 — knowledge-base-scoping Design §6.4.

- extra_metadata 지정 시 Qdrant payload와 ES body 양쪽에 전파
- 미지정 시 기존 동작 불변 (회귀 가드)
- 고정 키(document_id/user_id/collection_name) 충돌 시 고정 키 우선
"""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.unified_upload.schemas import UnifiedUploadRequest
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


def _make_activity_log_entry():
    return ActivityLogEntry(
        id=1,
        collection_name="my-collection",
        action=ActionType.CREATE,
        user_id="admin",
        detail={"embedding_model": "text-embedding-3-small"},
        created_at=datetime.now(),
    )


def _fake_chunk(content: str = "chunk text"):
    chunk = MagicMock()
    chunk.page_content = content
    chunk.metadata = {
        "chunk_id": str(uuid.uuid4()),
        "chunk_type": "child",
        "chunk_index": 0,
        "total_chunks": 1,
    }
    return chunk


def _make_morph_result() -> MorphAnalysisResult:
    return MorphAnalysisResult(
        tokens=(MorphToken(surface="문서", pos="NNG", start=0, length=2),),
        text="chunk text",
    )


def _build_use_case():
    deps = dict(
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
    return UnifiedUploadUseCase(**deps), deps


async def _run_upload(deps, request, chunks):
    deps["collection_repo"].collection_exists.return_value = True
    deps["activity_log_repo"].find_all.return_value = [_make_activity_log_entry()]
    deps["embedding_model_repo"].find_by_model_name.return_value = (
        _make_embedding_model()
    )
    deps["parser"].parse_bytes.return_value = [MagicMock()]

    mock_embedding = AsyncMock()
    mock_embedding.embed_documents.return_value = [[0.1] * 1536] * len(chunks)
    deps["embedding_factory"].create_from_string.return_value = mock_embedding

    deps["morph_analyzer"].analyze.return_value = _make_morph_result()
    deps["es_repo"].bulk_index.return_value = len(chunks)

    with patch(
        "src.application.unified_upload.use_case.ChunkingStrategyFactory"
    ) as mock_factory, patch(
        "src.application.unified_upload.use_case.QdrantVectorStore"
    ) as mock_vs_cls:
        mock_strategy = MagicMock()
        mock_strategy.chunk.return_value = chunks
        mock_factory.create_strategy.return_value = mock_strategy

        mock_vs = AsyncMock()
        mock_doc_id = MagicMock()
        mock_doc_id.value = "stored-id"
        mock_vs.add_documents.return_value = [mock_doc_id] * len(chunks)
        mock_vs_cls.return_value = mock_vs

        uc = UnifiedUploadUseCase(**deps)
        result = await uc.execute(request, "req-1")
        return result, mock_vs


class TestExtraMetadata:
    @pytest.mark.asyncio
    async def test_extra_metadata_propagates_to_qdrant_payload(self):
        _, deps = _build_use_case()
        request = _make_request(
            extra_metadata={"kb_id": "kb-uuid", "kb_name": "여신 규정집"}
        )
        _, mock_vs = await _run_upload(deps, request, [_fake_chunk()])

        stored_docs = mock_vs.add_documents.call_args[0][0]
        assert stored_docs[0].metadata["kb_id"] == "kb-uuid"
        assert stored_docs[0].metadata["kb_name"] == "여신 규정집"

    @pytest.mark.asyncio
    async def test_extra_metadata_propagates_to_es_body(self):
        _, deps = _build_use_case()
        request = _make_request(
            extra_metadata={"kb_id": "kb-uuid", "kb_name": "여신 규정집"}
        )
        await _run_upload(deps, request, [_fake_chunk()])

        es_docs = deps["es_repo"].bulk_index.call_args[0][0]
        assert es_docs[0].body["kb_id"] == "kb-uuid"
        assert es_docs[0].body["kb_name"] == "여신 규정집"

    @pytest.mark.asyncio
    async def test_without_extra_metadata_no_kb_fields(self):
        _, deps = _build_use_case()
        request = _make_request()
        _, mock_vs = await _run_upload(deps, request, [_fake_chunk()])

        stored_docs = mock_vs.add_documents.call_args[0][0]
        assert "kb_id" not in stored_docs[0].metadata

        es_docs = deps["es_repo"].bulk_index.call_args[0][0]
        assert "kb_id" not in es_docs[0].body

    @pytest.mark.asyncio
    async def test_kb_id_recorded_in_document_metadata(self):
        """kb-management-ui D2: extra_metadata.kb_id → DocumentMetadata.kb_id."""
        _, deps = _build_use_case()
        request = _make_request(
            extra_metadata={"kb_id": "kb-uuid", "kb_name": "여신 규정집"}
        )
        await _run_upload(deps, request, [_fake_chunk()])

        saved = deps["document_metadata_repo"].save.call_args[0][0]
        assert saved.kb_id == "kb-uuid"

    @pytest.mark.asyncio
    async def test_without_kb_id_document_metadata_none(self):
        """kb-management-ui D2 회귀 가드: 일반 업로드는 kb_id None."""
        _, deps = _build_use_case()
        request = _make_request()
        await _run_upload(deps, request, [_fake_chunk()])

        saved = deps["document_metadata_repo"].save.call_args[0][0]
        assert saved.kb_id is None

    @pytest.mark.asyncio
    async def test_fixed_keys_take_precedence_over_extra(self):
        _, deps = _build_use_case()
        request = _make_request(
            extra_metadata={"document_id": "hijack", "user_id": "hijack"}
        )
        _, mock_vs = await _run_upload(deps, request, [_fake_chunk()])

        stored_docs = mock_vs.add_documents.call_args[0][0]
        assert stored_docs[0].metadata["document_id"] != "hijack"
        assert stored_docs[0].metadata["user_id"] == "user-1"

        es_docs = deps["es_repo"].bulk_index.call_args[0][0]
        assert es_docs[0].body["document_id"] != "hijack"
        assert es_docs[0].body["user_id"] == "user-1"
