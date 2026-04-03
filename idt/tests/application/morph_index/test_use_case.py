"""MorphAndDualIndexUseCase tests — all external deps mocked."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document as LCDoc

from src.domain.morph.schemas import MorphAnalysisResult, MorphToken
from src.domain.morph_index.schemas import MorphIndexRequest, MorphIndexResult
from src.domain.vector.entities import Document as VecDoc
from src.domain.vector.value_objects import DocumentId
from src.application.morph_index.use_case import MorphAndDualIndexUseCase


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def mock_chunks():
    return [
        LCDoc(
            page_content="금융 정책 분석",
            metadata={
                "chunk_id": "cid-1",
                "chunk_type": "child",
                "chunk_index": 0,
                "total_chunks": 2,
            },
        ),
        LCDoc(
            page_content="이자율 좋다",
            metadata={
                "chunk_id": "cid-2",
                "chunk_type": "child",
                "chunk_index": 1,
                "total_chunks": 2,
            },
        ),
    ]


@pytest.fixture
def mock_morph_results():
    result1 = MorphAnalysisResult(
        tokens=(
            MorphToken("금융", "NNG", 0, 2),
            MorphToken("정책", "NNG", 3, 2),
            MorphToken("분석하", "VV", 6, 3),
        ),
        text="금융 정책 분석",
    )
    result2 = MorphAnalysisResult(
        tokens=(
            MorphToken("이자율", "NNG", 0, 3),
            MorphToken("좋", "VA", 4, 1),
        ),
        text="이자율 좋다",
    )
    return [result1, result2]


@pytest.fixture
def use_case(mock_chunks, mock_morph_results):
    chunking_strategy = MagicMock()
    chunking_strategy.chunk.return_value = mock_chunks

    morph_analyzer = MagicMock()
    morph_analyzer.analyze.side_effect = mock_morph_results

    embedding = MagicMock()
    embedding.embed_documents = AsyncMock(
        return_value=[[0.1] * 8, [0.2] * 8]
    )

    vector_store = MagicMock()
    vector_store.add_documents = AsyncMock(
        return_value=[DocumentId("cid-1"), DocumentId("cid-2")]
    )

    es_repo = MagicMock()
    es_repo.bulk_index = AsyncMock()

    logger = MagicMock()

    return MorphAndDualIndexUseCase(
        chunking_strategy=chunking_strategy,
        morph_analyzer=morph_analyzer,
        embedding=embedding,
        vector_store=vector_store,
        es_repo=es_repo,
        es_index="test-index",
        logger=logger,
    )


@pytest.fixture
def request_obj():
    return MorphIndexRequest(
        document_id="doc-1",
        content="금융 정책 분석 이자율 좋다",
        user_id="user-1",
        strategy_type="parent_child",
        source="report.pdf",
    )


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_returns_morph_index_result(use_case, request_obj):
    result = await use_case.execute(request_obj, "req-1")
    assert isinstance(result, MorphIndexResult)


@pytest.mark.asyncio
async def test_execute_calls_chunking_strategy(use_case, request_obj):
    await use_case.execute(request_obj, "req-1")
    use_case._chunking_strategy.chunk.assert_called_once()


@pytest.mark.asyncio
async def test_execute_calls_morph_analyzer_per_chunk(use_case, request_obj, mock_chunks):
    await use_case.execute(request_obj, "req-1")
    assert use_case._morph_analyzer.analyze.call_count == len(mock_chunks)


@pytest.mark.asyncio
async def test_execute_calls_embedding_with_all_chunk_texts(use_case, request_obj, mock_chunks):
    await use_case.execute(request_obj, "req-1")
    texts = [c.page_content for c in mock_chunks]
    use_case._embedding.embed_documents.assert_called_once_with(texts)


@pytest.mark.asyncio
async def test_execute_calls_vector_store_add_documents(use_case, request_obj):
    await use_case.execute(request_obj, "req-1")
    use_case._vector_store.add_documents.assert_called_once()


@pytest.mark.asyncio
async def test_execute_calls_es_bulk_index(use_case, request_obj):
    await use_case.execute(request_obj, "req-1")
    use_case._es_repo.bulk_index.assert_called_once()


@pytest.mark.asyncio
async def test_morph_keywords_vv_gets_da_suffix(use_case, request_obj):
    result = await use_case.execute(request_obj, "req-1")
    chunk0_keywords = result.indexed_chunks[0].morph_keywords
    assert "분석하다" in chunk0_keywords  # VV "분석하" → "분석하다"


@pytest.mark.asyncio
async def test_morph_keywords_va_gets_da_suffix(use_case, request_obj):
    result = await use_case.execute(request_obj, "req-1")
    chunk1_keywords = result.indexed_chunks[1].morph_keywords
    assert "좋다" in chunk1_keywords  # VA "좋" → "좋다"


@pytest.mark.asyncio
async def test_morph_keywords_nng_unchanged(use_case, request_obj):
    result = await use_case.execute(request_obj, "req-1")
    chunk0_keywords = result.indexed_chunks[0].morph_keywords
    assert "금융" in chunk0_keywords
    assert "정책" in chunk0_keywords


@pytest.mark.asyncio
async def test_char_start_end_set_in_indexed_chunk(use_case, request_obj):
    result = await use_case.execute(request_obj, "req-1")
    for chunk in result.indexed_chunks:
        assert chunk.char_start >= 0
        assert chunk.char_end > chunk.char_start


@pytest.mark.asyncio
async def test_total_chunks_matches_indexed(use_case, request_obj, mock_chunks):
    result = await use_case.execute(request_obj, "req-1")
    assert result.total_chunks == len(mock_chunks)
    assert len(result.indexed_chunks) == len(mock_chunks)


@pytest.mark.asyncio
async def test_logs_start_and_completion(use_case, request_obj):
    await use_case.execute(request_obj, "req-1")
    assert use_case._logger.info.call_count >= 2


@pytest.mark.asyncio
async def test_error_in_chunking_logs_and_raises(use_case, request_obj):
    use_case._chunking_strategy.chunk.side_effect = RuntimeError("chunk fail")
    with pytest.raises(RuntimeError):
        await use_case.execute(request_obj, "req-1")
    use_case._logger.error.assert_called_once()
