"""추출 도메인 — 추출 단위·언급·관계 VO 와 순수 정책.

Design Ref: graph-rag-foundation §2.2(적재)·§3.4(결정적 ID)·§11.4 V1.
V1 확인(2026-11-17): ES 에 parent·child 가 모두 저장된다 → parent 가 있으면
parent 만 추출 단위로 쓴다(문맥이 넓고 LLM 호출 수가 적다). 요약 청크는 제외.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# 추출 규칙·판정이 바뀌면 올린다 — resume 도 이전 버전 청크는 다시 추출한다.
# v2 (2026-11-17): 조문 머리·제목 관계, 값 엔티티 청크 단위 키, LLM 언급 우선.
# v3 (2026-11-17): module-4 판정(후보 검색·Jev·LLM), 이름 임베딩·별칭, 관계 방향 규칙.
EXTRACTOR_VERSION = "v3"
GLOBAL_SCOPE = "global"

_NS = uuid.UUID("6f3c1a52-8e0b-4f7e-9a1d-0c5b2e9d4a11")
_SUMMARY_TYPES = frozenset({"section_summary", "document_summary"})
_PARENT, _CHILD = "parent", "child"
_EDGE_CHARS = " \t\r\n.,;:!?\"'`()[]{}<>「」『』《》〈〉【】“”‘’"
_WS = re.compile(r"\s+")
MIN_EVIDENCE_CHARS = 4


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


ACTIVE_JOB_STATUSES = frozenset({JobStatus.PENDING, JobStatus.PROCESSING})


class JobMode(StrEnum):
    RESUME = "resume"  # 같은 추출기 버전으로 끝난 청크는 건너뜀
    REBUILD = "rebuild"  # 문서 그래프를 지우고 처음부터


class TriggerSource(StrEnum):
    UPLOAD = "upload"
    ADMIN = "admin"


@dataclass(frozen=True)
class ChunkUnit:
    chunk_id: str
    document_id: str
    kb_id: str | None
    collection_name: str
    content: str
    chunk_index: int


REL_RELATES = "RELATES"
REL_REFERS_TO = "REFERS_TO"


@dataclass(frozen=True)
class Mention:
    name: str  # 표시 이름(원문)
    type: str
    description: str
    chunk_id: str
    key: str | None = (
        None  # 정규화 키 직접 지정(조문은 문서 단위 키) — 없으면 이름 정규화
    )

    @property
    def lookup_key(self) -> str:
        return self.key or NameNormalizer.normalize(self.name)


@dataclass(frozen=True)
class RelationDraft:
    source: str  # 언급 이름 또는 Mention.key
    target: str
    type: str
    evidence: str
    chunk_id: str
    kind: str = REL_RELATES


@dataclass(frozen=True)
class EntityWrite:
    id: str
    scope_key: str
    name: str
    normalized_name: str
    type: str
    description: str
    name_embedding: tuple[float, ...] | None = None  # module-4 후보 벡터 검색용


@dataclass(frozen=True)
class MentionWrite:
    entity_id: str
    decision_id: str


@dataclass(frozen=True)
class AliasWrite:
    """기존 엔티티에 다른 표기로 연결될 때 남기는 별칭 (module-4)."""

    entity_id: str
    scope_key: str
    normalized: str
    surface: str


@dataclass(frozen=True)
class RelationWrite:
    id: str
    kind: str
    source_entity_id: str
    target_entity_id: str
    type: str
    evidence_text: str
    source_decision_id: str
    target_decision_id: str


@dataclass(frozen=True)
class ChunkGraphWrite:
    """청크 1개분 그래프 쓰기 — 한 트랜잭션으로 저장한다(재실행 시 같은 결과)."""

    unit: ChunkUnit
    extractor_version: str
    new_entities: tuple[EntityWrite, ...]
    mentions: tuple[MentionWrite, ...]
    relations: tuple[RelationWrite, ...]
    aliases: tuple[AliasWrite, ...] = ()


@dataclass(frozen=True)
class ExtractionContext:
    model_id: str
    entity_types: tuple[str, ...]
    relation_types: tuple[str, ...]
    request_id: str


@dataclass(frozen=True)
class ExtractionResult:
    mentions: tuple[Mention, ...] = ()
    relations: tuple[RelationDraft, ...] = ()
    llm_calls: int = 0


@dataclass
class ExtractionJob:
    id: str
    document_id: str
    kb_id: str | None
    collection_name: str
    status: JobStatus
    mode: JobMode
    trigger_source: TriggerSource
    extractor_version: str = EXTRACTOR_VERSION
    total_chunks: int = 0
    processed_chunks: int = 0
    failed_chunks: int = 0
    llm_calls: int = 0
    judge_calls: int = 0
    entities_created: int = 0
    entities_linked: int = 0
    relations_created: int = 0
    error_message: str | None = None
    requested_by: str | None = None
    started_at: Any = None
    finished_at: Any = None
    created_at: Any = None
    updated_at: Any = None


@dataclass
class JobCounters:
    processed_chunks: int = 0
    failed_chunks: int = 0
    llm_calls: int = 0
    judge_calls: int = 0
    entities_created: int = 0
    entities_linked: int = 0
    relations_created: int = 0
    skipped_chunks: list[str] = field(default_factory=list)


class ExtractionUnitPolicy:
    @staticmethod
    def select(docs: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        candidates = [
            d
            for d in docs
            if d.get("chunk_type") not in _SUMMARY_TYPES
            and str(d.get("content") or "").strip()
        ]
        if any(d.get("chunk_type") == _PARENT for d in candidates):
            candidates = [d for d in candidates if d.get("chunk_type") != _CHILD]
        return sorted(candidates, key=lambda d: int(d.get("chunk_index") or 0))


class EvidencePolicy:
    """관계 근거 문장이 청크 원문에 실제로 있는지 (Plan FR-06 — 없으면 버림)."""

    @staticmethod
    def is_grounded(evidence: str | None, chunk_text: str) -> bool:
        ev = _WS.sub(" ", (evidence or "").strip())
        if len(ev) < MIN_EVIDENCE_CHARS:
            return False
        return ev in _WS.sub(" ", chunk_text)


class DocumentEligibilityPolicy:
    """그래프 추출 대상 문서인지 — 업로드 훅·관리자 수동 실행이 같은 규칙을 쓴다.

    표 데이터(엑셀·CSV)는 '항목=값' 행이 값 자체를 엔티티로 만들어 그래프 품질을
    떨어뜨린다(2026-11-17 실추출 확인). 표 분석은 기존 엑셀 분석 기능이 맡는다.
    """

    _TABULAR = (".xlsx", ".xls", ".csv")

    @classmethod
    def is_extractable(cls, filename: str | None) -> bool:
        return not (filename or "").strip().lower().endswith(cls._TABULAR)


class LiteralValuePolicy:
    """이름 자체가 값(금액·비율·기간·날짜)인지 — 값 엔티티는 청크 밖과 연결하지 않는다.

    2026-11-17 실추출: "연 4.2%", "최장 36개월"이 독립 엔티티가 됐다. 같은 값이 다른
    문서·문맥의 엔티티와 이름만으로 합쳐지면 잘못된 경로가 생긴다. 타입 이름
    (예: '수치기준')을 코드에 두지 않고 이름의 모양으로 판단한다(일반화 원칙).
    숫자와 단위를 지운 뒤 남는 글자가 2자 이하면 값으로 본다.
    """

    _UNITS = re.compile(
        r"%p|bp|억원|만원|천원|개월|개년|시간|[%원억만천년월일주배건명회분초]"
    )
    _NON_WORD = re.compile(r"[\s\d.,~\-+/()·:]+")
    _CLAUSE = re.compile(r"^제\s*\d+\s*조")
    MAX_RESIDUAL_CHARS = 2

    @classmethod
    def is_literal(cls, name: str) -> bool:
        text = unicodedata.normalize("NFKC", name or "").strip()
        if not any(ch.isdigit() for ch in text) or cls._CLAUSE.match(text):
            return False
        residual = cls._NON_WORD.sub("", cls._UNITS.sub("", text.casefold()))
        return len(residual) <= cls.MAX_RESIDUAL_CHARS


class NameNormalizer:
    """정규화 키 — 표시 이름(원문)은 별도로 보존한다. 조사 제거는 module-4(Kiwi)."""

    @staticmethod
    def normalize(name: str) -> str:
        text = unicodedata.normalize("NFKC", name or "")
        text = _WS.sub(" ", text).strip(_EDGE_CHARS)
        return text.casefold()


def decision_id_for(chunk_id: str, normalized: str, type_: str) -> str:
    return str(uuid.uuid5(_NS, f"decision:{chunk_id}:{normalized}:{type_}"))


def relation_id_for(chunk_id: str, src_norm: str, type_: str, tgt_norm: str) -> str:
    return str(uuid.uuid5(_NS, f"relation:{chunk_id}:{src_norm}:{type_}:{tgt_norm}"))
