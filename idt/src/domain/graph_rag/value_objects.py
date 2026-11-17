"""graph_rag 도메인 VO.

Design Ref: graph-rag-foundation §3.1 — GraphRagSettings.__post_init__ 가 값 검증의
단일 출처다(라우터·저장소는 다시 검증하지 않는다). 기본 타입 목록은 V086 시드와 같은
데이터이며, 행이 없을 때의 안전 기본값으로만 쓴다(코어 하드코딩 아님).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

OTHER_TYPE = "기타"
MAX_TYPES = 30
MAX_TYPE_LEN = 32

DEFAULT_ENTITY_TYPES: tuple[str, ...] = (
    "상품·서비스",
    "대상",
    "조건·요건",
    "규정·문서",
    "조문",
    "용어",
    "조직·부서",
    "수치기준",
    "절차",
    OTHER_TYPE,
)
DEFAULT_RELATION_TYPES: tuple[str, ...] = (
    "적용대상",
    "요건",
    "예외",
    "한도",
    "정의",
    "참조",
    "포함",
    "담당",
    OTHER_TYPE,
)


class RolloutStage(StrEnum):
    OFF = "off"
    ADMIN_ONLY = "admin_only"
    GENERAL = "general"

    @classmethod
    def from_string(cls, raw: str | None) -> RolloutStage:
        """대소문자·양끝 공백 무시.

        빈 값·오타는 ValueError(조용히 off 로 바꾸지 않음).
        """
        normalized = (raw or "").strip().casefold()
        for stage in cls:
            if stage.value == normalized:
                return stage
        allowed = ", ".join(s.value for s in cls)
        raise ValueError(f"unknown rollout stage {raw!r} (allowed: {allowed})")


def _require_range(name: str, value: float, lo: float, hi: float) -> None:
    if isinstance(value, bool) or not (lo <= value <= hi):
        raise ValueError(f"{name} must be between {lo} and {hi}, got {value!r}")


def _normalize_types(name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = tuple(v.strip() for v in values)
    if any(not v or len(v) > MAX_TYPE_LEN for v in cleaned):
        raise ValueError(f"{name}: each type must be 1~{MAX_TYPE_LEN} chars")
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"{name}: types must be unique")
    if OTHER_TYPE not in cleaned:
        raise ValueError(f"{name}: must include {OTHER_TYPE!r}")
    if len(cleaned) > MAX_TYPES:
        raise ValueError(f"{name}: at most {MAX_TYPES} types")
    return cleaned


MAX_RETRIEVAL_TIMEOUT_MS = 5000


@dataclass(frozen=True)
class GraphRagSettings:
    rollout_stage: RolloutStage
    extraction_enabled: bool
    jev_enabled: bool
    link_threshold: float
    new_threshold: float
    extraction_llm_model_id: str | None
    rejudge_llm_model_id: str | None
    concurrency: int
    max_llm_calls_per_doc: int
    candidate_top_k: int
    max_hops: int
    graph_rrf_weight: float
    retrieval_timeout_ms: int
    entity_types: tuple[str, ...]
    relation_types: tuple[str, ...]
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_range("link_threshold", self.link_threshold, 0.0, 1.0)
        if not 0.0 < self.new_threshold < self.link_threshold:
            raise ValueError(
                "thresholds must satisfy 0 < new_threshold < link_threshold"
            )
        _require_range("concurrency", self.concurrency, 1, 8)
        _require_range("max_llm_calls_per_doc", self.max_llm_calls_per_doc, 1, 2000)
        _require_range("candidate_top_k", self.candidate_top_k, 1, 8)
        _require_range("max_hops", self.max_hops, 1, 3)
        _require_range("graph_rrf_weight", self.graph_rrf_weight, 0.0, 1.0)
        _require_range(
            "retrieval_timeout_ms",
            self.retrieval_timeout_ms,
            100,
            MAX_RETRIEVAL_TIMEOUT_MS,
        )
        object.__setattr__(
            self,
            "entity_types",
            _normalize_types("entity_types", tuple(self.entity_types)),
        )
        object.__setattr__(
            self,
            "relation_types",
            _normalize_types("relation_types", tuple(self.relation_types)),
        )

    @property
    def effective_rejudge_model_id(self) -> str | None:
        return self.rejudge_llm_model_id or self.extraction_llm_model_id

    @classmethod
    def defaults(cls) -> GraphRagSettings:
        """V086 시드와 같은 값 — 행이 없거나 읽기 실패 시의 닫힌 기본값."""
        return cls(
            rollout_stage=RolloutStage.OFF,
            extraction_enabled=False,
            jev_enabled=False,
            link_threshold=0.8,
            new_threshold=0.4,
            extraction_llm_model_id=None,
            rejudge_llm_model_id=None,
            concurrency=3,
            max_llm_calls_per_doc=300,
            candidate_top_k=5,
            max_hops=2,
            graph_rrf_weight=0.5,
            retrieval_timeout_ms=800,
            entity_types=DEFAULT_ENTITY_TYPES,
            relation_types=DEFAULT_RELATION_TYPES,
        )


@dataclass(frozen=True)
class StageChange:
    id: str
    from_stage: RolloutStage
    to_stage: RolloutStage
    changed_by: str
    eval_baseline_run_id: str | None
    eval_graph_run_id: str | None
    force_reason: str | None
    created_at: datetime


@dataclass(frozen=True)
class GraphHealth:
    backend: str  # "off" | "neo4j"
    connected: bool
    external: bool  # Aura 등 외부 클라우드 저장 여부 (Design §7)
    node_count: int | None = None
    relationship_count: int | None = None
    node_limit: int | None = None
    relationship_limit: int | None = None
    error: str | None = None
