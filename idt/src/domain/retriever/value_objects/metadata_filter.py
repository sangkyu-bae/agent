"""MetadataFilter value object for retriever domain.

Provides filtering capabilities for document retrieval operations.
Supports conversion to Qdrant-specific filter format.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from qdrant_client.models import Filter, FieldCondition, MatchValue, Range


VALID_CHUNK_TYPES = frozenset({"parent", "child", "full", "semantic"})


@dataclass(frozen=True)
class MetadataFilter:
    """Value object for document retrieval filtering.

    Supports filtering by:
    - user_id: Filter by user identifier
    - session_id: Filter by session identifier
    - document_id: Filter by document identifier
    - chunk_type: Filter by chunk type (parent/child/full/semantic)
    - parent_id: Filter by parent document identifier
    - date_from/date_to: Filter by date range
    - custom_filters: Additional key-value filters
    """

    user_id: Optional[str] = None
    session_id: Optional[str] = None
    document_id: Optional[str] = None
    chunk_type: Optional[str] = None
    parent_id: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    custom_filters: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Validate filter values."""
        if self.chunk_type is not None and self.chunk_type not in VALID_CHUNK_TYPES:
            raise ValueError(
                f"Invalid chunk_type: {self.chunk_type}. "
                f"Must be one of: {', '.join(sorted(VALID_CHUNK_TYPES))}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert filter to dictionary representation.

        Returns:
            Dictionary with non-None filter values.
            Custom filters are flattened into the dict.
        """
        result: Dict[str, Any] = {}

        if self.user_id is not None:
            result["user_id"] = self.user_id
        if self.session_id is not None:
            result["session_id"] = self.session_id
        if self.document_id is not None:
            result["document_id"] = self.document_id
        if self.chunk_type is not None:
            result["chunk_type"] = self.chunk_type
        if self.parent_id is not None:
            result["parent_id"] = self.parent_id
        if self.date_from is not None:
            result["date_from"] = self.date_from
        if self.date_to is not None:
            result["date_to"] = self.date_to

        if self.custom_filters:
            for key, value in self.custom_filters.items():
                result[key] = value

        return result

    def is_empty(self) -> bool:
        """Check if filter has no conditions set.

        Returns:
            True if no filter conditions are set, False otherwise.
        """
        has_custom = bool(self.custom_filters)

        return (
            self.user_id is None
            and self.session_id is None
            and self.document_id is None
            and self.chunk_type is None
            and self.parent_id is None
            and self.date_from is None
            and self.date_to is None
            and not has_custom
        )

    def merge(self, other: "MetadataFilter") -> "MetadataFilter":
        """Merge with another filter, other values take precedence.

        Args:
            other: The filter to merge with (its values override self)

        Returns:
            New MetadataFilter with merged values
        """
        merged_custom: Optional[Dict[str, Any]] = None

        if self.custom_filters or other.custom_filters:
            merged_custom = {}
            if self.custom_filters:
                merged_custom.update(self.custom_filters)
            if other.custom_filters:
                merged_custom.update(other.custom_filters)

        return MetadataFilter(
            user_id=other.user_id if other.user_id is not None else self.user_id,
            session_id=(
                other.session_id if other.session_id is not None else self.session_id
            ),
            document_id=(
                other.document_id
                if other.document_id is not None
                else self.document_id
            ),
            chunk_type=(
                other.chunk_type if other.chunk_type is not None else self.chunk_type
            ),
            parent_id=(
                other.parent_id if other.parent_id is not None else self.parent_id
            ),
            date_from=(
                other.date_from if other.date_from is not None else self.date_from
            ),
            date_to=other.date_to if other.date_to is not None else self.date_to,
            custom_filters=merged_custom,
        )

    def to_qdrant_filter(self) -> Optional[Filter]:
        """Convert to Qdrant Filter object.

        Returns:
            Qdrant Filter with must conditions, or None if empty.
        """
        conditions: list[FieldCondition] = []

        if self.user_id is not None:
            conditions.append(
                FieldCondition(key="user_id", match=MatchValue(value=self.user_id))
            )

        if self.session_id is not None:
            conditions.append(
                FieldCondition(
                    key="session_id", match=MatchValue(value=self.session_id)
                )
            )

        if self.document_id is not None:
            conditions.append(
                FieldCondition(
                    key="document_id", match=MatchValue(value=self.document_id)
                )
            )

        if self.chunk_type is not None:
            conditions.append(
                FieldCondition(
                    key="chunk_type", match=MatchValue(value=self.chunk_type)
                )
            )

        if self.parent_id is not None:
            conditions.append(
                FieldCondition(key="parent_id", match=MatchValue(value=self.parent_id))
            )

        if self.date_from is not None or self.date_to is not None:
            conditions.append(
                FieldCondition(
                    key="created_at",
                    range=Range(
                        gte=self.date_from.timestamp() if self.date_from else None,
                        lte=self.date_to.timestamp() if self.date_to else None,
                    ),
                )
            )

        if self.custom_filters:
            for key, value in self.custom_filters.items():
                conditions.append(
                    FieldCondition(key=key, match=MatchValue(value=value))
                )

        if not conditions:
            return None

        return Filter(must=conditions)
