from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class DistanceMetric(str, Enum):
    COSINE = "Cosine"
    EUCLID = "Euclid"
    DOT = "Dot"


class ActionType(str, Enum):
    CREATE = "CREATE"
    DELETE = "DELETE"
    RENAME = "RENAME"
    LIST = "LIST"
    DETAIL = "DETAIL"
    SEARCH = "SEARCH"
    ADD_DOCUMENT = "ADD_DOCUMENT"
    DELETE_DOCUMENT = "DELETE_DOCUMENT"
    CHANGE_SCOPE = "CHANGE_SCOPE"


@dataclass(frozen=True)
class CollectionInfo:
    name: str
    vectors_count: int
    points_count: int
    status: str


@dataclass(frozen=True)
class CollectionDetail:
    name: str
    vectors_count: int
    points_count: int
    status: str
    vector_size: int
    distance: str


@dataclass(frozen=True)
class CreateCollectionRequest:
    name: str
    vector_size: int
    distance: DistanceMetric = DistanceMetric.COSINE
    embedding_model: str | None = None


@dataclass(frozen=True)
class ActivityLogEntry:
    id: int
    collection_name: str
    action: ActionType
    user_id: str | None
    detail: dict[str, Any] | None
    created_at: datetime
