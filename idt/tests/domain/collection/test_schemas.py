from datetime import datetime

import pytest

from src.domain.collection.schemas import (
    ActionType,
    ActivityLogEntry,
    CollectionDetail,
    CollectionInfo,
    CreateCollectionRequest,
    DistanceMetric,
)


class TestDistanceMetric:
    def test_values(self) -> None:
        assert DistanceMetric.COSINE.value == "Cosine"
        assert DistanceMetric.EUCLID.value == "Euclid"
        assert DistanceMetric.DOT.value == "Dot"

    def test_from_string(self) -> None:
        assert DistanceMetric("Cosine") is DistanceMetric.COSINE


class TestActionType:
    def test_all_values(self) -> None:
        expected = {
            "CREATE", "DELETE", "RENAME", "LIST",
            "DETAIL", "SEARCH", "ADD_DOCUMENT", "DELETE_DOCUMENT",
            "CHANGE_SCOPE",
        }
        assert {a.value for a in ActionType} == expected


class TestCollectionInfo:
    def test_frozen(self) -> None:
        info = CollectionInfo("docs", 10, 10, "green")
        with pytest.raises(AttributeError):
            info.name = "other"


class TestCreateCollectionRequest:
    def test_default_distance(self) -> None:
        req = CreateCollectionRequest(name="test", vector_size=1536)
        assert req.distance is DistanceMetric.COSINE


class TestActivityLogEntry:
    def test_construction(self) -> None:
        entry = ActivityLogEntry(
            id=1,
            collection_name="docs",
            action=ActionType.SEARCH,
            user_id=None,
            detail={"q": "test"},
            created_at=datetime(2026, 1, 1),
        )
        assert entry.action is ActionType.SEARCH
        assert entry.user_id is None
