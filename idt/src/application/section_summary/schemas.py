"""Section Summary application 스키마 (card-section-summary Design §7)."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SectionSummaryLaunchInput:
    """KB 업로드 완료 시점의 런처 입력 — 잡 스냅샷 재료 (D11/D14)."""

    document_id: str
    kb_id: str
    collection_name: str
    profile_id: str
    llm_model_id: str
    embedding_model_name: str


@dataclass(frozen=True)
class SectionSummaryLaunchInfo:
    """업로드 응답에 실리는 잡 킥오프 정보 (D15)."""

    job_id: str
    status: str


@dataclass(frozen=True)
class SectionSummaryJobStatus:
    """상태 조회/재시도 응답 (§7.2)."""

    job_id: str
    document_id: str
    status: str
    total_sections: int | None
    done_sections: int
    failed_sections: int
    is_stale: bool
    error: str | None
    created_at: datetime | None
    updated_at: datetime | None


class SectionSummaryRetryNotAllowedError(Exception):
    """재시도 불가 상태(완료됨/진행 중이며 stale 아님) — 라우터가 409로 매핑."""
