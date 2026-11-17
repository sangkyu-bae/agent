"""문서 주제 도메인 — 2단계 주제(대분류 > 소분류)와 문서↔주제 연결.

Design Ref: graph-rag-foundation §11.9 (module-4b), Plan FR-25~29.
주제는 그래프 탐색 경로가 아니라 검색 범위다. 판정 기록은 V089 를 재사용하고
`mention_type` 으로 엔티티 판정과 구분한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from src.domain.graph_rag.exceptions import GraphTopicInvalidError
from src.domain.graph_rag.extraction import _NS, ChunkUnit, NameNormalizer

DOCUMENT_CHUNK_ID = "__document__"  # 주제 판정은 문서 단위 — V089 chunk_id 자리
TOPIC_TYPE_PREFIX = "주제:"
MAX_TOPIC_NAME = 64
MAX_TOPIC_DESCRIPTION = 500
MAX_SECONDARY_TOPICS = 2
MAX_TOPIC_CANDIDATES = 30
TOPIC_EXCERPT_CHUNKS = 3
TOPIC_EXCERPT_CHARS = 3000


class TopicLevel(IntEnum):
    MAJOR = 1
    MINOR = 2


class TopicStatus(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"  # 자동 생성 — 검토 전에도 검색 범위에는 쓴다
    RETIRED = "retired"


class TopicOrigin(StrEnum):
    ADMIN = "admin"
    AUTO = "auto"


_MENTION_TYPES = {TopicLevel.MAJOR: "주제:대분류", TopicLevel.MINOR: "주제:소분류"}


def mention_type_for(level: TopicLevel) -> str:
    return _MENTION_TYPES[level]


def level_of_mention_type(mention_type: str) -> TopicLevel:
    for level, value in _MENTION_TYPES.items():
        if value == mention_type:
            return level
    raise ValueError(f"not a topic mention type: {mention_type!r}")


def is_topic_decision(mention_type: str) -> bool:
    return mention_type.startswith(TOPIC_TYPE_PREFIX)


def topic_decision_id(document_id: str, slot: str) -> str:
    """slot: major / minor / secondary0 / secondary1 — 재분류해도 같은 id."""
    return str(uuid.uuid5(_NS, f"topic:{document_id}:{slot}"))


@dataclass(frozen=True)
class Topic:
    id: str
    name: str
    normalized_name: str
    level: TopicLevel
    parent_id: str | None
    description: str
    status: TopicStatus
    origin: TopicOrigin
    created_by: str | None = None
    created_at: object = None
    updated_at: object = None

    @property
    def parent_key(self) -> str:
        return self.parent_id or ""

    @property
    def usable(self) -> bool:
        return self.status is not TopicStatus.RETIRED


@dataclass(frozen=True)
class DocumentTopic:
    document_id: str
    topic_id: str
    is_primary: bool
    probability: float | None
    decision_id: str


@dataclass(frozen=True)
class TopicSuggestion:
    name: str
    description: str = ""


@dataclass(frozen=True)
class TopicProposal:
    """LLM 제안 — 대표 대분류·소분류 + 보조 대분류 이름."""

    major: TopicSuggestion
    minor: TopicSuggestion | None = None
    secondary: tuple[str, ...] = ()


class TopicPolicy:
    @staticmethod
    def clean_name(name: str) -> str:
        cleaned = " ".join((name or "").split())
        if not cleaned or len(cleaned) > MAX_TOPIC_NAME:
            raise GraphTopicInvalidError(
                f"topic name must be 1..{MAX_TOPIC_NAME} chars"
            )
        return cleaned

    @staticmethod
    def normalize(name: str) -> str:
        return NameNormalizer.normalize(name)[:MAX_TOPIC_NAME]

    @staticmethod
    def check_parent(level: TopicLevel, parent_id: str | None) -> None:
        if level is TopicLevel.MAJOR and parent_id:
            raise GraphTopicInvalidError("major topic cannot have a parent")
        if level is TopicLevel.MINOR and not parent_id:
            raise GraphTopicInvalidError("minor topic needs a parent major topic")

    @staticmethod
    def excerpt(units: list[ChunkUnit]) -> str:
        """문서 앞부분 — 청크 순서대로 앞 3개, 최대 3,000자."""
        first = sorted(units, key=lambda u: u.chunk_index)[:TOPIC_EXCERPT_CHUNKS]
        return "\n".join(u.content for u in first)[:TOPIC_EXCERPT_CHARS]
