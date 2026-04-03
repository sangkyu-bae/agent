"""Tests for RetrievalUseCase.

TDD: tests written before implementation.
Uses Mock — no real Qdrant/OpenAI calls.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.retrieval.schemas import RetrievalRequest, RetrievalResult
from src.domain.vector.entities import Document
from src.domain.vector.value_objects import DocumentId
from src.infrastructure.retriever.parent_child_retriever import ParentChildResult


def _make_domain_doc(doc_id: str, content: str, score: float = 0.9, parent_id: str = "p1") -> Document:
    return Document(
        id=DocumentId(doc_id),
        content=content,
        vector=[0.1] * 10,
        metadata={"chunk_type": "child", "parent_id": parent_id, "user_id": "user_1"},
        score=score,
    )


def _make_parent_doc(parent_id: str, content: str) -> Document:
    return Document(
        id=DocumentId(parent_id),
        content=content,
        vector=[0.1] * 10,
        metadata={"chunk_type": "parent"},
        score=None,
    )


def _make_parent_child_result(child_id: str, parent_id: str, score: float = 0.9) -> ParentChildResult:
    child = _make_domain_doc(child_id, f"child content {child_id}", score, parent_id)
    parent = _make_parent_doc(parent_id, f"parent content {parent_id}")
    return ParentChildResult(child=child, parent=parent, score=score, sibling_count=1)


@pytest.fixture
def mock_retriever():
    retriever = AsyncMock()
    retriever.retrieve_with_parent = AsyncMock(return_value=[
        _make_parent_child_result("c1", "p1", 0.92),
        _make_parent_child_result("c2", "p1", 0.85),
    ])
    retriever.retrieve_with_scores = AsyncMock(return_value=[
        (_make_domain_doc("c1", "content 1", 0.92), 0.92),
    ])
    return retriever


@pytest.fixture
def mock_compressor():
    from langchain_core.documents import Document as LCDoc
    compressor = AsyncMock()
    compressor.compress = AsyncMock(return_value=[
        LCDoc(page_content="child content c1", metadata={"chunk_type": "child", "parent_id": "p1", "user_id": "user_1"}),
    ])
    return compressor


@pytest.fixture
def mock_query_rewriter():
    from src.domain.query_rewrite.value_objects import RewrittenQuery
    rewriter = AsyncMock()
    rewriter.rewrite = AsyncMock(return_value=RewrittenQuery(
        original_query="금리 인상",
        rewritten_query="금리 인상이 채권 가격에 미치는 영향",
    ))
    return rewriter


@pytest.fixture
def mock_logger():
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    return logger


@pytest.fixture
def use_case(mock_retriever, mock_compressor, mock_logger):
    from src.application.retrieval.retrieval_use_case import RetrievalUseCase
    return RetrievalUseCase(
        retriever=mock_retriever,
        compressor=mock_compressor,
        query_rewriter=None,
        logger=mock_logger,
    )


class TestRetrievalUseCaseExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_documents(self, use_case, mock_retriever):
        """Normal retrieval returns documents."""
        request = RetrievalRequest(
            query="금리 인상",
            user_id="user_1",
            request_id="req_1",
            top_k=10,
            use_parent_context=True,
            use_compression=False,
        )
        result = await use_case.execute(request)

        assert isinstance(result, RetrievalResult)
        assert len(result.documents) == 2
        assert result.query == "금리 인상"
        assert result.rewritten_query is None
        assert result.total_found == 2
        assert result.request_id == "req_1"

    @pytest.mark.asyncio
    async def test_execute_with_compression(self, use_case, mock_compressor):
        """Compression filters documents."""
        request = RetrievalRequest(
            query="금리 인상",
            user_id="user_1",
            request_id="req_1",
            use_parent_context=True,
            use_compression=True,
        )
        result = await use_case.execute(request)

        mock_compressor.compress.assert_awaited_once()
        assert result.total_found == 1

    @pytest.mark.asyncio
    async def test_execute_without_parent_context(self, use_case, mock_retriever):
        """use_parent_context=False uses basic retrieve_with_scores."""
        request = RetrievalRequest(
            query="금리 인상",
            user_id="user_1",
            request_id="req_1",
            use_parent_context=False,
            use_compression=False,
        )
        result = await use_case.execute(request)

        mock_retriever.retrieve_with_scores.assert_awaited_once()
        assert len(result.documents) == 1

    @pytest.mark.asyncio
    async def test_execute_with_query_rewrite(self, mock_retriever, mock_compressor, mock_query_rewriter, mock_logger):
        """use_query_rewrite=True rewrites query before retrieval."""
        from src.application.retrieval.retrieval_use_case import RetrievalUseCase
        uc = RetrievalUseCase(
            retriever=mock_retriever,
            compressor=mock_compressor,
            query_rewriter=mock_query_rewriter,
            logger=mock_logger,
        )
        request = RetrievalRequest(
            query="금리 인상",
            user_id="user_1",
            request_id="req_1",
            use_query_rewrite=True,
            use_compression=False,
        )
        result = await uc.execute(request)

        mock_query_rewriter.rewrite.assert_awaited_once_with(
            query="금리 인상", request_id="req_1"
        )
        assert result.rewritten_query == "금리 인상이 채권 가격에 미치는 영향"

    @pytest.mark.asyncio
    async def test_execute_raises_on_empty_query(self, use_case):
        """Empty query raises ValueError."""
        request = RetrievalRequest(
            query="",
            user_id="user_1",
            request_id="req_1",
        )
        with pytest.raises(ValueError, match="Query is required"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_raises_on_short_query(self, use_case):
        """Single-char query raises ValueError."""
        request = RetrievalRequest(
            query="a",
            user_id="user_1",
            request_id="req_1",
        )
        with pytest.raises(ValueError):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_logs_start_and_complete(self, use_case, mock_logger):
        """Logger receives info calls for start and completion."""
        request = RetrievalRequest(
            query="금리 인상",
            user_id="user_1",
            request_id="req_1",
            use_compression=False,
        )
        await use_case.execute(request)

        assert mock_logger.info.call_count >= 2

    @pytest.mark.asyncio
    async def test_execute_document_includes_parent_content(self, use_case):
        """Result documents include parent_content when use_parent_context=True."""
        request = RetrievalRequest(
            query="금리 인상",
            user_id="user_1",
            request_id="req_1",
            use_parent_context=True,
            use_compression=False,
        )
        result = await use_case.execute(request)

        assert result.documents[0].parent_content is not None
        assert "parent content" in result.documents[0].parent_content

    @pytest.mark.asyncio
    async def test_execute_applies_metadata_filter_with_document_id(self, use_case, mock_retriever):
        """document_id filter is passed to retriever."""
        request = RetrievalRequest(
            query="금리 인상",
            user_id="user_1",
            request_id="req_1",
            document_id="doc_001",
            use_compression=False,
        )
        await use_case.execute(request)

        call_args = mock_retriever.retrieve_with_parent.call_args
        filters = call_args.kwargs.get("filters") or call_args.args[2] if len(call_args.args) > 2 else None
        if filters is None and call_args.kwargs:
            filters = call_args.kwargs.get("filters")
        assert filters is not None
        assert filters.document_id == "doc_001"
