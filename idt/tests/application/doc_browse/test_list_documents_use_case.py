from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.doc_browse.list_documents_use_case import ListDocumentsUseCase
from src.domain.doc_browse.schemas import DocumentMetadata
from src.domain.mysql.schemas import MySQLPageResult


def _metadata(doc_id: str, filename: str = "a.pdf") -> DocumentMetadata:
    return DocumentMetadata(
        document_id=doc_id,
        collection_name="test-col",
        filename=filename,
        category="policy",
        user_id="u1",
        chunk_count=5,
        chunk_strategy="parent_child",
    )


def _make_use_case(
    page_items: list[DocumentMetadata] | None = None,
    total: int = 0,
    limit: int = 20,
    offset: int = 0,
) -> ListDocumentsUseCase:
    items = page_items or []
    mock_repo = AsyncMock()
    mock_repo.find_by_collection = AsyncMock(
        return_value=MySQLPageResult(
            items=items, total=total, limit=limit, offset=offset
        )
    )
    logger = MagicMock()
    return ListDocumentsUseCase(document_metadata_repo=mock_repo, logger=logger)


@pytest.mark.asyncio
async def test_returns_correct_response_format():
    items = [_metadata("doc-1"), _metadata("doc-2", "b.pdf")]
    uc = _make_use_case(page_items=items, total=2)
    result = await uc.execute("test-col", offset=0, limit=20)

    assert result["collection_name"] == "test-col"
    assert result["total_documents"] == 2
    assert result["offset"] == 0
    assert result["limit"] == 20
    assert len(result["documents"]) == 2


@pytest.mark.asyncio
async def test_document_fields_mapping():
    items = [_metadata("doc-1")]
    uc = _make_use_case(page_items=items, total=1)
    result = await uc.execute("test-col")

    doc = result["documents"][0]
    assert doc["document_id"] == "doc-1"
    assert doc["filename"] == "a.pdf"
    assert doc["category"] == "policy"
    assert doc["chunk_count"] == 5
    assert doc["chunk_types"] == []
    assert doc["user_id"] == "u1"


@pytest.mark.asyncio
async def test_passes_pagination_to_repo():
    mock_repo = AsyncMock()
    mock_repo.find_by_collection = AsyncMock(
        return_value=MySQLPageResult(items=[], total=0, limit=10, offset=5)
    )
    uc = ListDocumentsUseCase(document_metadata_repo=mock_repo, logger=MagicMock())

    result = await uc.execute("test-col", offset=5, limit=10)

    call_kwargs = mock_repo.find_by_collection.call_args
    pagination = call_kwargs.kwargs.get("pagination") or call_kwargs[1].get("pagination")
    assert pagination.limit == 10
    assert pagination.offset == 5


@pytest.mark.asyncio
async def test_returns_empty_for_no_documents():
    uc = _make_use_case(page_items=[], total=0)
    result = await uc.execute("empty-col")

    assert result["documents"] == []
    assert result["total_documents"] == 0


@pytest.mark.asyncio
async def test_propagates_repository_exception():
    mock_repo = AsyncMock()
    mock_repo.find_by_collection = AsyncMock(side_effect=RuntimeError("DB down"))
    uc = ListDocumentsUseCase(document_metadata_repo=mock_repo, logger=MagicMock())

    with pytest.raises(RuntimeError, match="DB down"):
        await uc.execute("test-col")
