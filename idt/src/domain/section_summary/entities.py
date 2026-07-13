"""SectionSummary 도메인 엔티티 (card-section-summary Design §5, D1/D3).

카드 섹션(=clause-aware parent 청크)별 키워드+3줄 요약 생성 잡과
그 산출물을 표현한다. 외부 시스템 호출 없이 순수 값만 보관.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime

JOB_STATUS_PENDING = "pending"
JOB_STATUS_PROCESSING = "processing"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"


def summary_id_for(section_ref: str) -> str:
    """섹션 참조 기반 결정적 요약 ID — 재시도 멱등 upsert의 근거 (D5)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"section-summary:{section_ref}"))


def document_summary_id_for(document_id: str) -> str:
    """문서 요약 결정적 ID — 문서당 1 point 멱등 (document-summary-routing D10)."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"document-summary:{document_id}")
    )


@dataclass(frozen=True)
class SectionCard:
    """요약 대상 카드 섹션 하나 — v1 소스는 parent(조) 청크 (D1).

    meta: 원 청크 payload 통과분(user_id/kb_name/filename 등) —
    요약 저장 시 공통 필드로 재사용한다.
    """

    section_ref: str  # 원 parent chunk_id (rawchunk 확장 연결고리)
    title: str        # clause_title
    text: str
    chunk_index: int = 0
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SectionSummaryItem:
    """저장된 섹션 요약 1건 — 문서 요약의 입력 (document-summary-routing D6)."""

    title: str      # clause_title
    summary: str    # 3줄 요약 텍스트
    keywords: list[str]
    chunk_index: int = 0
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentSummaryRecord:
    """문서 요약 저장 계약 — 문서당 1건 (document-summary-routing §4)."""

    summary_id: str
    document_id: str
    collection_name: str
    kb_id: str
    kb_name: str
    user_id: str
    keywords: list[str]
    summary_text: str
    vector: list[float]
    section_count: int
    filename: str = ""


@dataclass(frozen=True)
class SectionSummarySpec:
    """업로드 완료 시점에 resolver가 해석한 요약 실행 사양 (D14)."""

    llm_model_id: str
    profile_id: str


@dataclass(frozen=True)
class SectionSummaryResult:
    """LLM이 산출한 섹션 요약 (Policy 방어 절단 후)."""

    keywords: list[str]
    summary_lines: list[str]

    @property
    def summary_text(self) -> str:
        return "\n".join(self.summary_lines)


@dataclass(frozen=True)
class SectionSummaryRecord:
    """저장소(Qdrant/ES)에 기록할 요약 1건의 완전한 계약 (Design §5.1/5.2)."""

    summary_id: str
    section_ref: str
    document_id: str
    collection_name: str
    kb_id: str
    kb_name: str
    user_id: str
    clause_title: str
    chunk_index: int
    keywords: list[str]
    summary_text: str
    vector: list[float]
    filename: str = ""


@dataclass
class SectionSummaryJob:
    """섹션 요약 백그라운드 잡 — 문서당 1행 (D3)."""

    id: str
    document_id: str
    kb_id: str
    collection_name: str
    chunking_profile_id: str
    llm_model_id: str
    embedding_provider: str
    embedding_model: str
    status: str = JOB_STATUS_PENDING
    total_sections: int | None = None
    done_sections: int = 0
    failed_sections: int = 0
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
