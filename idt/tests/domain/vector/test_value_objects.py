"""Tests for vector domain value objects.

TDD: These tests are written first before implementation.
Domain tests use NO mocks as per CLAUDE.md rules.
"""
import pytest
from datetime import date

from src.domain.vector.value_objects import (
    DocumentId,
    DocumentType,
    DateRange,
    SearchFilter,
)


class TestDocumentId:
    """Tests for DocumentId value object."""

    def test_create_valid_document_id(self) -> None:
        doc_id = DocumentId("doc-123")
        assert doc_id.value == "doc-123"

    def test_document_id_equality(self) -> None:
        doc_id1 = DocumentId("doc-123")
        doc_id2 = DocumentId("doc-123")
        assert doc_id1 == doc_id2

    def test_document_id_inequality(self) -> None:
        doc_id1 = DocumentId("doc-123")
        doc_id2 = DocumentId("doc-456")
        assert doc_id1 != doc_id2

    def test_empty_document_id_raises_error(self) -> None:
        with pytest.raises(ValueError, match="DocumentId cannot be empty"):
            DocumentId("")

    def test_whitespace_only_document_id_raises_error(self) -> None:
        with pytest.raises(ValueError, match="DocumentId cannot be empty"):
            DocumentId("   ")

    def test_document_id_is_immutable(self) -> None:
        doc_id = DocumentId("doc-123")
        with pytest.raises(AttributeError):
            doc_id.value = "doc-456"


class TestDocumentType:
    """Tests for DocumentType value object.

    Document types represent categories of documents in the RAG system.
    """

    def test_policy_type(self) -> None:
        doc_type = DocumentType.POLICY
        assert doc_type.value == "policy"

    def test_faq_type(self) -> None:
        doc_type = DocumentType.FAQ
        assert doc_type.value == "faq"

    def test_manual_type(self) -> None:
        doc_type = DocumentType.MANUAL
        assert doc_type.value == "manual"

    def test_notice_type(self) -> None:
        doc_type = DocumentType.NOTICE
        assert doc_type.value == "notice"

    def test_from_string_policy(self) -> None:
        doc_type = DocumentType.from_string("policy")
        assert doc_type == DocumentType.POLICY

    def test_from_string_faq(self) -> None:
        doc_type = DocumentType.from_string("faq")
        assert doc_type == DocumentType.FAQ

    def test_from_string_invalid_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid document type"):
            DocumentType.from_string("unknown")

    def test_from_string_case_insensitive(self) -> None:
        doc_type = DocumentType.from_string("POLICY")
        assert doc_type == DocumentType.POLICY


class TestDateRange:
    """Tests for DateRange value object.

    DateRange is used for filtering documents by date.
    """

    def test_create_valid_date_range(self) -> None:
        start = date(2024, 1, 1)
        end = date(2024, 12, 31)
        date_range = DateRange(start_date=start, end_date=end)
        assert date_range.start_date == start
        assert date_range.end_date == end

    def test_date_range_with_same_start_and_end(self) -> None:
        same_date = date(2024, 6, 15)
        date_range = DateRange(start_date=same_date, end_date=same_date)
        assert date_range.start_date == date_range.end_date

    def test_date_range_end_before_start_raises_error(self) -> None:
        start = date(2024, 12, 31)
        end = date(2024, 1, 1)
        with pytest.raises(ValueError, match="end_date must be >= start_date"):
            DateRange(start_date=start, end_date=end)

    def test_date_range_equality(self) -> None:
        range1 = DateRange(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        range2 = DateRange(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        assert range1 == range2

    def test_date_range_is_immutable(self) -> None:
        date_range = DateRange(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        with pytest.raises(AttributeError):
            date_range.start_date = date(2025, 1, 1)

    def test_date_range_contains_date_inside(self) -> None:
        date_range = DateRange(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        assert date_range.contains(date(2024, 6, 15)) is True

    def test_date_range_contains_date_on_start_boundary(self) -> None:
        date_range = DateRange(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        assert date_range.contains(date(2024, 1, 1)) is True

    def test_date_range_contains_date_on_end_boundary(self) -> None:
        date_range = DateRange(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        assert date_range.contains(date(2024, 12, 31)) is True

    def test_date_range_contains_date_outside_before(self) -> None:
        date_range = DateRange(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        assert date_range.contains(date(2023, 12, 31)) is False

    def test_date_range_contains_date_outside_after(self) -> None:
        date_range = DateRange(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        assert date_range.contains(date(2025, 1, 1)) is False


class TestSearchFilter:
    """Tests for SearchFilter value object.

    SearchFilter combines multiple filter conditions for vector search.
    """

    def test_create_empty_filter(self) -> None:
        search_filter = SearchFilter()
        assert search_filter.document_type is None
        assert search_filter.date_range is None
        assert search_filter.metadata == {}

    def test_create_filter_with_document_type(self) -> None:
        search_filter = SearchFilter(document_type=DocumentType.POLICY)
        assert search_filter.document_type == DocumentType.POLICY

    def test_create_filter_with_date_range(self) -> None:
        date_range = DateRange(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        search_filter = SearchFilter(date_range=date_range)
        assert search_filter.date_range == date_range

    def test_create_filter_with_metadata(self) -> None:
        metadata = {"category": "finance", "status": "active"}
        search_filter = SearchFilter(metadata=metadata)
        assert search_filter.metadata == metadata

    def test_create_filter_with_all_options(self) -> None:
        date_range = DateRange(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        metadata = {"category": "finance"}
        search_filter = SearchFilter(
            document_type=DocumentType.POLICY,
            date_range=date_range,
            metadata=metadata,
        )
        assert search_filter.document_type == DocumentType.POLICY
        assert search_filter.date_range == date_range
        assert search_filter.metadata == metadata

    def test_filter_is_empty_true(self) -> None:
        search_filter = SearchFilter()
        assert search_filter.is_empty() is True

    def test_filter_is_empty_false_with_document_type(self) -> None:
        search_filter = SearchFilter(document_type=DocumentType.FAQ)
        assert search_filter.is_empty() is False

    def test_filter_is_empty_false_with_date_range(self) -> None:
        date_range = DateRange(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        search_filter = SearchFilter(date_range=date_range)
        assert search_filter.is_empty() is False

    def test_filter_is_empty_false_with_metadata(self) -> None:
        search_filter = SearchFilter(metadata={"key": "value"})
        assert search_filter.is_empty() is False

    def test_filter_equality(self) -> None:
        filter1 = SearchFilter(document_type=DocumentType.POLICY)
        filter2 = SearchFilter(document_type=DocumentType.POLICY)
        assert filter1 == filter2

    def test_filter_is_immutable(self) -> None:
        search_filter = SearchFilter(document_type=DocumentType.POLICY)
        with pytest.raises(AttributeError):
            search_filter.document_type = DocumentType.FAQ
