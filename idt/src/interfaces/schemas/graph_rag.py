"""graph-rag-foundation API 스키마 (Design §4).

형식 검증만 한다 — 값 범위 검증은 도메인 VO GraphRagSettings 가 단일 출처.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.domain.graph_rag.value_objects import (
    GraphHealth,
    GraphRagSettings,
    StageChange,
)


class GraphRagSettingsRequest(BaseModel):
    extraction_enabled: bool
    jev_enabled: bool
    link_threshold: float
    new_threshold: float
    extraction_llm_model_id: str | None = None
    rejudge_llm_model_id: str | None = None
    concurrency: int
    max_llm_calls_per_doc: int
    candidate_top_k: int
    max_hops: int
    graph_rrf_weight: float
    retrieval_timeout_ms: int
    entity_types: list[str]
    relation_types: list[str]


class GraphRagSettingsResponse(GraphRagSettingsRequest):
    rollout_stage: str
    updated_at: datetime | None = None

    @classmethod
    def from_domain(cls, s: GraphRagSettings) -> GraphRagSettingsResponse:
        return cls(
            rollout_stage=s.rollout_stage.value,
            extraction_enabled=s.extraction_enabled,
            jev_enabled=s.jev_enabled,
            link_threshold=s.link_threshold,
            new_threshold=s.new_threshold,
            extraction_llm_model_id=s.extraction_llm_model_id,
            rejudge_llm_model_id=s.rejudge_llm_model_id,
            concurrency=s.concurrency,
            max_llm_calls_per_doc=s.max_llm_calls_per_doc,
            candidate_top_k=s.candidate_top_k,
            max_hops=s.max_hops,
            graph_rrf_weight=s.graph_rrf_weight,
            retrieval_timeout_ms=s.retrieval_timeout_ms,
            entity_types=list(s.entity_types),
            relation_types=list(s.relation_types),
            updated_at=s.updated_at,
        )


class StageChangeRequest(BaseModel):
    to_stage: str
    eval_baseline_run_id: str | None = Field(default=None, max_length=36)
    eval_graph_run_id: str | None = Field(default=None, max_length=36)
    force_reason: str | None = Field(default=None, max_length=500)


class StageChangeItem(BaseModel):
    id: str
    from_stage: str
    to_stage: str
    changed_by: str
    eval_baseline_run_id: str | None
    eval_graph_run_id: str | None
    force_reason: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, c: StageChange) -> StageChangeItem:
        return cls(
            id=c.id,
            from_stage=c.from_stage.value,
            to_stage=c.to_stage.value,
            changed_by=c.changed_by,
            eval_baseline_run_id=c.eval_baseline_run_id,
            eval_graph_run_id=c.eval_graph_run_id,
            force_reason=c.force_reason,
            created_at=c.created_at,
        )


class StageHistoryResponse(BaseModel):
    items: list[StageChangeItem]


class GraphHealthResponse(BaseModel):
    backend: str
    connected: bool
    external: bool
    node_count: int | None = None
    relationship_count: int | None = None
    node_limit: int | None = None
    relationship_limit: int | None = None
    error: str | None = None

    @classmethod
    def from_domain(cls, h: GraphHealth) -> GraphHealthResponse:
        return cls(**h.__dict__)


class CapabilitiesResponse(BaseModel):
    visible: bool
    stage: str | None = None
