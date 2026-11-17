"""관리자 점검용 VO — 엔티티 목록·상세, 근거 정합성 (module-5b).

Design Ref: graph-rag-foundation §4.1 entities·integrity, Plan FR-16, SC-2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_ENTITY_PAGE_SIZE = 100
MAX_DETAIL_RELATIONS = 100
MAX_DETAIL_MENTIONS = 50
MAX_INTEGRITY_SAMPLE = 2000
MAX_INTEGRITY_LISTED = 20
PREVIEW_CHARS = 200


@dataclass(frozen=True)
class EntitySummary:
    id: str
    name: str
    type: str
    description: str
    mention_count: int
    relation_count: int


@dataclass(frozen=True)
class RelationView:
    id: str
    direction: str  # out | in
    kind: str  # RELATES | REFERS_TO
    type: str
    other_id: str
    other_name: str
    evidence_chunk_id: str
    evidence_text: str
    document_id: str


@dataclass(frozen=True)
class MentionView:
    chunk_id: str
    document_id: str
    decision_id: str
    preview: str = ""


@dataclass
class EntityDetail:
    entity: EntitySummary
    aliases: list[str] = field(default_factory=list)
    relations: list[RelationView] = field(default_factory=list)
    mentions: list[MentionView] = field(default_factory=list)


@dataclass(frozen=True)
class GraphChunkRef:
    chunk_id: str
    document_id: str


@dataclass(frozen=True)
class IntegrityReport:
    checked: int
    missing: int
    missing_chunk_ids: tuple[str, ...]
    missing_document_ids: tuple[str, ...]
