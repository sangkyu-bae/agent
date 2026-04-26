from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.doc_browse.schemas import DocumentMetadata
from src.domain.mysql.schemas import MySQLPaginationParams
from src.infrastructure.doc_browse.document_metadata_repository import (
    DocumentMetadataRepository,
)
from src.infrastructure.doc_browse.models import DocumentMetadataModel


def _metadata(
    doc_id: str = "doc-1",
    collection: str = "test-col",
    filename: str = "a.pdf",
) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=doc_id,
        collection_name=collection,
        filename=filename,
        category="policy",
        user_id="user1",
        chunk_count=10,
        chunk_strategy="parent_child",
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_logger() -> MagicMock:
    return MagicMock()


@pytest.fixture
def repo(mock_session: AsyncMock, mock_logger: MagicMock) -> DocumentMetadataRepository:
    return DocumentMetadataRepository(mock_session, mock_logger)


class TestSave:
    async def test_inserts_new_document(
        self, repo: DocumentMetadataRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        await repo.save(_metadata(), request_id="req-1")

        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        model = mock_session.add.call_args[0][0]
        assert isinstance(model, DocumentMetadataModel)
        assert model.document_id == "doc-1"
        assert model.filename == "a.pdf"
        assert model.chunk_count == 10

    async def test_updates_existing_document(
        self, repo: DocumentMetadataRepository, mock_session: AsyncMock
    ) -> None:
        existing = DocumentMetadataModel(
            document_id="doc-1",
            collection_name="test-col",
            filename="old.pdf",
            category="old",
            user_id="user1",
            chunk_count=5,
            chunk_strategy="fixed",
        )
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
        )

        updated = _metadata(filename="new.pdf")
        await repo.save(updated, request_id="req-2")

        assert existing.filename == "new.pdf"
        assert existing.chunk_count == 10
        assert existing.chunk_strategy == "parent_child"
        mock_session.add.assert_not_called()
        mock_session.flush.assert_awaited_once()

    async def test_raises_on_db_error(
        self, repo: DocumentMetadataRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB error"))

        with pytest.raises(RuntimeError, match="DB error"):
            await repo.save(_metadata(), request_id="req-3")


class TestFindByCollection:
    async def test_returns_paginated_results(
        self, repo: DocumentMetadataRepository, mock_session: AsyncMock
    ) -> None:
        models = [
            DocumentMetadataModel(
                document_id=f"doc-{i}",
                collection_name="test-col",
                filename=f"{i}.pdf",
                category="policy",
                user_id="u1",
                chunk_count=i + 1,
                chunk_strategy="fixed",
            )
            for i in range(3)
        ]

        count_result = MagicMock(scalar_one=MagicMock(return_value=10))
        query_result = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=models))))
        mock_session.execute = AsyncMock(side_effect=[count_result, query_result])

        pagination = MySQLPaginationParams(limit=3, offset=0)
        page = await repo.find_by_collection("test-col", "req-4", pagination)

        assert page.total == 10
        assert len(page.items) == 3
        assert page.limit == 3
        assert page.offset == 0
        assert page.items[0].document_id == "doc-0"

    async def test_returns_empty_for_no_documents(
        self, repo: DocumentMetadataRepository, mock_session: AsyncMock
    ) -> None:
        count_result = MagicMock(scalar_one=MagicMock(return_value=0))
        query_result = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        mock_session.execute = AsyncMock(side_effect=[count_result, query_result])

        page = await repo.find_by_collection("empty-col", "req-5")

        assert page.total == 0
        assert page.items == []

    async def test_uses_default_pagination(
        self, repo: DocumentMetadataRepository, mock_session: AsyncMock
    ) -> None:
        count_result = MagicMock(scalar_one=MagicMock(return_value=0))
        query_result = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        mock_session.execute = AsyncMock(side_effect=[count_result, query_result])

        page = await repo.find_by_collection("test-col", "req-6")

        assert page.limit == 20
        assert page.offset == 0


class TestDeleteByDocumentId:
    async def test_deletes_existing_document(
        self, repo: DocumentMetadataRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute = AsyncMock(
            return_value=MagicMock(rowcount=1)
        )

        result = await repo.delete_by_document_id("doc-1", "req-7")

        assert result is True
        mock_session.flush.assert_awaited_once()

    async def test_returns_false_for_missing_document(
        self, repo: DocumentMetadataRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute = AsyncMock(
            return_value=MagicMock(rowcount=0)
        )

        result = await repo.delete_by_document_id("nonexistent", "req-8")

        assert result is False


class TestFindByDocumentId:
    async def test_returns_metadata_when_exists(
        self, repo: DocumentMetadataRepository, mock_session: AsyncMock
    ) -> None:
        model = DocumentMetadataModel(
            document_id="doc-1",
            collection_name="test-col",
            filename="a.pdf",
            category="policy",
            user_id="u1",
            chunk_count=5,
            chunk_strategy="fixed",
        )
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=model))
        )

        result = await repo.find_by_document_id("doc-1", "req-9")

        assert result is not None
        assert result.document_id == "doc-1"
        assert result.filename == "a.pdf"

    async def test_returns_none_when_not_found(
        self, repo: DocumentMetadataRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        result = await repo.find_by_document_id("nonexistent", "req-10")

        assert result is None
