"""graph-rag-foundation API 스키마 (Design §4).

형식 검증만 한다 — 값 범위 검증은 도메인 VO GraphRagSettings 가 단일 출처.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.domain.graph_rag.extraction import ExtractionJob
from src.domain.graph_rag.resolution import ResolutionDecision
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


# ── module-3: 추출 잡 ──────────────────────────────────────────────────────


class ExtractRequest(BaseModel):
    mode: Literal["resume", "rebuild"] = "resume"


class ExtractAcceptedResponse(BaseModel):
    job_id: str
    status: str


class ExtractionJobResponse(BaseModel):
    id: str
    document_id: str
    kb_id: str | None
    collection_name: str
    status: str
    mode: str
    trigger_source: str
    extractor_version: str
    total_chunks: int
    processed_chunks: int
    failed_chunks: int
    llm_calls: int
    judge_calls: int
    entities_created: int
    entities_linked: int
    relations_created: int
    error_message: str | None
    requested_by: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime | None

    @classmethod
    def from_domain(cls, j: ExtractionJob) -> ExtractionJobResponse:
        data = {k: getattr(j, k) for k in cls.model_fields}
        for k in ("status", "mode", "trigger_source"):
            data[k] = getattr(j, k).value
        return cls(**data)


class KbDocumentJobItem(BaseModel):
    document_id: str
    filename: str
    chunk_count: int
    job: ExtractionJobResponse | None


class KbDocumentJobsResponse(BaseModel):
    items: list[KbDocumentJobItem]
    total: int


# ── module-4: 검토 큐 ──────────────────────────────────────────────────────


class ReviewItem(BaseModel):
    id: str
    job_id: str
    document_id: str
    chunk_id: str
    mention_text: str
    mention_type: str
    candidates: list[dict]
    probabilities: dict[str, float] | None
    chosen_label: str
    entity_id: str
    created_new: bool
    decided_by: str
    band: str
    probability: float | None
    llm_confidence: str | None
    llm_reason: str | None
    review_status: str
    created_at: datetime | None

    @classmethod
    def from_domain(cls, d: ResolutionDecision) -> ReviewItem:
        return cls(
            id=d.id,
            job_id=d.job_id,
            document_id=d.document_id,
            chunk_id=d.chunk_id,
            mention_text=d.mention_text,
            mention_type=d.mention_type,
            candidates=list(d.candidates),
            probabilities=d.probabilities,
            chosen_label=d.chosen_label,
            entity_id=d.entity_id,
            created_new=d.created_new,
            decided_by=d.decided_by.value,
            band=d.band.value,
            probability=d.probability,
            llm_confidence=d.llm_confidence.value if d.llm_confidence else None,
            llm_reason=d.llm_reason,
            review_status=d.review_status.value,
            created_at=d.created_at,
        )


class ReviewListResponse(BaseModel):
    items: list[ReviewItem]
    total: int


class ReviewApproveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class ReviewRejectRequest(BaseModel):
    target_entity_id: str | None = Field(default=None, max_length=36)
    note: str | None = Field(default=None, max_length=500)


class ReviewRejectResponse(BaseModel):
    entity_id: str
