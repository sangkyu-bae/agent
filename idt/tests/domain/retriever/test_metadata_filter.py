"""Tests for MetadataFilter value object.

Tests:
- Filter creation with various fields
- chunk_type validation (parent/child/full/semantic)
- to_dict() method
- is_empty() method
- merge() method
- to_qdrant_filter() conversion
"""
import pytest
from datetime import datetime
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

from src.domain.retriever.value_objects.metadata_filter import MetadataFilter


class TestMetadataFilterCreation:
    """Tests for MetadataFilter creation."""

    def test_create_empty_filter(self):
        """Should create filter with no conditions."""
        filter = MetadataFilter()
        assert filter.user_id is None
        assert filter.session_id is None
        assert filter.document_id is None
        assert filter.chunk_type is None
        assert filter.parent_id is None
        assert filter.date_from is None
        assert filter.date_to is None
        assert filter.custom_filters is None

    def test_create_filter_with_user_id(self):
        """Should create filter with user_id."""
        filter = MetadataFilter(user_id="user-123")
        assert filter.user_id == "user-123"

    def test_create_filter_with_session_id(self):
        """Should create filter with session_id."""
        filter = MetadataFilter(session_id="session-456")
        assert filter.session_id == "session-456"

    def test_create_filter_with_document_id(self):
        """Should create filter with document_id."""
        filter = MetadataFilter(document_id="doc-789")
        assert filter.document_id == "doc-789"

    def test_create_filter_with_parent_id(self):
        """Should create filter with parent_id."""
        filter = MetadataFilter(parent_id="parent-001")
        assert filter.parent_id == "parent-001"

    def test_create_filter_with_date_range(self):
        """Should create filter with date range."""
        date_from = datetime(2024, 1, 1)
        date_to = datetime(2024, 12, 31)
        filter = MetadataFilter(date_from=date_from, date_to=date_to)
        assert filter.date_from == date_from
        assert filter.date_to == date_to

    def test_create_filter_with_custom_filters(self):
        """Should create filter with custom filters."""
        custom = {"department": "finance", "priority": "high"}
        filter = MetadataFilter(custom_filters=custom)
        assert filter.custom_filters == custom

    def test_create_filter_with_all_fields(self):
        """Should create filter with all fields populated."""
        date_from = datetime(2024, 1, 1)
        date_to = datetime(2024, 12, 31)
        custom = {"department": "finance"}

        filter = MetadataFilter(
            user_id="user-123",
            session_id="session-456",
            document_id="doc-789",
            chunk_type="child",
            parent_id="parent-001",
            date_from=date_from,
            date_to=date_to,
            custom_filters=custom,
        )

        assert filter.user_id == "user-123"
        assert filter.session_id == "session-456"
        assert filter.document_id == "doc-789"
        assert filter.chunk_type == "child"
        assert filter.parent_id == "parent-001"
        assert filter.date_from == date_from
        assert filter.date_to == date_to
        assert filter.custom_filters == custom


class TestChunkTypeValidation:
    """Tests for chunk_type validation."""

    @pytest.mark.parametrize(
        "chunk_type",
        ["parent", "child", "full", "semantic"],
    )
    def test_valid_chunk_types(self, chunk_type):
        """Should accept valid chunk types."""
        filter = MetadataFilter(chunk_type=chunk_type)
        assert filter.chunk_type == chunk_type

    def test_invalid_chunk_type_raises_error(self):
        """Should raise error for invalid chunk type."""
        with pytest.raises(ValueError) as exc_info:
            MetadataFilter(chunk_type="invalid")
        assert "chunk_type" in str(exc_info.value).lower()

    def test_none_chunk_type_is_valid(self):
        """Should accept None as chunk_type."""
        filter = MetadataFilter(chunk_type=None)
        assert filter.chunk_type is None


class TestToDict:
    """Tests for to_dict() method."""

    def test_empty_filter_to_dict(self):
        """Empty filter should return empty dict."""
        filter = MetadataFilter()
        result = filter.to_dict()
        assert result == {}

    def test_filter_with_fields_to_dict(self):
        """Filter with fields should return dict with those fields."""
        filter = MetadataFilter(
            user_id="user-123",
            document_id="doc-789",
            chunk_type="child",
        )
        result = filter.to_dict()
        assert result == {
            "user_id": "user-123",
            "document_id": "doc-789",
            "chunk_type": "child",
        }

    def test_filter_with_date_range_to_dict(self):
        """Filter with dates should include them in dict."""
        date_from = datetime(2024, 1, 1)
        date_to = datetime(2024, 12, 31)
        filter = MetadataFilter(date_from=date_from, date_to=date_to)
        result = filter.to_dict()
        assert result["date_from"] == date_from
        assert result["date_to"] == date_to

    def test_filter_with_custom_filters_to_dict(self):
        """Custom filters should be flattened into dict."""
        custom = {"department": "finance", "priority": "high"}
        filter = MetadataFilter(custom_filters=custom)
        result = filter.to_dict()
        assert result["department"] == "finance"
        assert result["priority"] == "high"


class TestIsEmpty:
    """Tests for is_empty() method."""

    def test_empty_filter_is_empty(self):
        """Filter with no conditions should be empty."""
        filter = MetadataFilter()
        assert filter.is_empty() is True

    def test_filter_with_user_id_is_not_empty(self):
        """Filter with user_id should not be empty."""
        filter = MetadataFilter(user_id="user-123")
        assert filter.is_empty() is False

    def test_filter_with_custom_filters_is_not_empty(self):
        """Filter with custom_filters should not be empty."""
        filter = MetadataFilter(custom_filters={"key": "value"})
        assert filter.is_empty() is False

    def test_filter_with_empty_custom_filters_is_empty(self):
        """Filter with empty custom_filters dict should be empty."""
        filter = MetadataFilter(custom_filters={})
        assert filter.is_empty() is True


class TestMerge:
    """Tests for merge() method."""

    def test_merge_empty_filters(self):
        """Merging two empty filters should produce empty filter."""
        filter1 = MetadataFilter()
        filter2 = MetadataFilter()
        merged = filter1.merge(filter2)
        assert merged.is_empty() is True

    def test_merge_overwrites_with_other_values(self):
        """Other filter values should overwrite self values."""
        filter1 = MetadataFilter(user_id="user-1", document_id="doc-1")
        filter2 = MetadataFilter(user_id="user-2")
        merged = filter1.merge(filter2)
        assert merged.user_id == "user-2"
        assert merged.document_id == "doc-1"

    def test_merge_preserves_self_when_other_is_none(self):
        """Self values should be preserved when other has None."""
        filter1 = MetadataFilter(user_id="user-1", chunk_type="child")
        filter2 = MetadataFilter(document_id="doc-2")
        merged = filter1.merge(filter2)
        assert merged.user_id == "user-1"
        assert merged.chunk_type == "child"
        assert merged.document_id == "doc-2"

    def test_merge_combines_custom_filters(self):
        """Custom filters should be merged."""
        filter1 = MetadataFilter(custom_filters={"key1": "val1"})
        filter2 = MetadataFilter(custom_filters={"key2": "val2"})
        merged = filter1.merge(filter2)
        assert merged.custom_filters == {"key1": "val1", "key2": "val2"}

    def test_merge_other_custom_filter_overwrites(self):
        """Other custom filter should overwrite same key."""
        filter1 = MetadataFilter(custom_filters={"key1": "val1"})
        filter2 = MetadataFilter(custom_filters={"key1": "val2"})
        merged = filter1.merge(filter2)
        assert merged.custom_filters["key1"] == "val2"


class TestToQdrantFilter:
    """Tests for to_qdrant_filter() method."""

    def test_empty_filter_returns_none(self):
        """Empty filter should return None."""
        filter = MetadataFilter()
        result = filter.to_qdrant_filter()
        assert result is None

    def test_user_id_filter(self):
        """Should create FieldCondition for user_id."""
        filter = MetadataFilter(user_id="user-123")
        result = filter.to_qdrant_filter()
        assert isinstance(result, Filter)
        assert len(result.must) == 1
        condition = result.must[0]
        assert condition.key == "user_id"
        assert condition.match.value == "user-123"

    def test_session_id_filter(self):
        """Should create FieldCondition for session_id."""
        filter = MetadataFilter(session_id="session-456")
        result = filter.to_qdrant_filter()
        assert isinstance(result, Filter)
        condition = result.must[0]
        assert condition.key == "session_id"
        assert condition.match.value == "session-456"

    def test_document_id_filter(self):
        """Should create FieldCondition for document_id."""
        filter = MetadataFilter(document_id="doc-789")
        result = filter.to_qdrant_filter()
        condition = result.must[0]
        assert condition.key == "document_id"
        assert condition.match.value == "doc-789"

    def test_chunk_type_filter(self):
        """Should create FieldCondition for chunk_type."""
        filter = MetadataFilter(chunk_type="child")
        result = filter.to_qdrant_filter()
        condition = result.must[0]
        assert condition.key == "chunk_type"
        assert condition.match.value == "child"

    def test_parent_id_filter(self):
        """Should create FieldCondition for parent_id."""
        filter = MetadataFilter(parent_id="parent-001")
        result = filter.to_qdrant_filter()
        condition = result.must[0]
        assert condition.key == "parent_id"
        assert condition.match.value == "parent-001"

    def test_date_range_filter(self):
        """Should create Range condition for date range."""
        date_from = datetime(2024, 1, 1)
        date_to = datetime(2024, 12, 31)
        filter = MetadataFilter(date_from=date_from, date_to=date_to)
        result = filter.to_qdrant_filter()

        condition = result.must[0]
        assert condition.key == "created_at"
        assert condition.range.gte == date_from.timestamp()
        assert condition.range.lte == date_to.timestamp()

    def test_date_from_only_filter(self):
        """Should handle date_from without date_to."""
        date_from = datetime(2024, 1, 1)
        filter = MetadataFilter(date_from=date_from)
        result = filter.to_qdrant_filter()

        condition = result.must[0]
        assert condition.key == "created_at"
        assert condition.range.gte == date_from.timestamp()
        assert condition.range.lte is None

    def test_date_to_only_filter(self):
        """Should handle date_to without date_from."""
        date_to = datetime(2024, 12, 31)
        filter = MetadataFilter(date_to=date_to)
        result = filter.to_qdrant_filter()

        condition = result.must[0]
        assert condition.key == "created_at"
        assert condition.range.gte is None
        assert condition.range.lte == date_to.timestamp()

    def test_custom_filters(self):
        """Should create FieldConditions for custom filters."""
        filter = MetadataFilter(custom_filters={"department": "finance"})
        result = filter.to_qdrant_filter()

        condition = result.must[0]
        assert condition.key == "department"
        assert condition.match.value == "finance"

    def test_multiple_conditions(self):
        """Should combine multiple conditions."""
        filter = MetadataFilter(
            user_id="user-123",
            document_id="doc-789",
            chunk_type="child",
        )
        result = filter.to_qdrant_filter()
        assert len(result.must) == 3


class TestImmutability:
    """Tests for filter immutability."""

    def test_filter_is_frozen(self):
        """MetadataFilter should be immutable."""
        filter = MetadataFilter(user_id="user-123")
        with pytest.raises(Exception):
            filter.user_id = "user-456"

    def test_merge_returns_new_instance(self):
        """Merge should return new instance, not modify original."""
        filter1 = MetadataFilter(user_id="user-1")
        filter2 = MetadataFilter(document_id="doc-2")
        merged = filter1.merge(filter2)

        assert merged is not filter1
        assert merged is not filter2
        assert filter1.document_id is None
        assert filter2.user_id is None
