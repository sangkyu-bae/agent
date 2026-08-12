"""document_generator 도메인 스키마 (doc-generator Design §4-2).

⚠️ 외부 의존(DB·LangChain·파일 I/O) 금지 — 순수 값/규칙만.
"""
from dataclasses import dataclass, field
from datetime import datetime

GENERATION_TYPE_STATUS_ACTIVE = "active"
GENERATION_TYPE_STATUS_DELETED = "deleted"


@dataclass(frozen=True)
class DocumentSection:
    """섹션 아웃라인 한 항목. title은 산출 HTML heading으로 강제된다 (D2)."""

    title: str
    guidance: str = ""  # 작성 지침 — 조사 방향·포함할 내용 (D3 소스 힌트 표현처)


@dataclass
class DocumentGenerationType:
    """그 에이전트·그 도구 전용 문서 유형 (공유/fork 없음 — 추출기 템플릿 동형)."""

    id: str
    agent_id: str
    worker_id: str
    name: str
    description: str
    sections: list[DocumentSection]
    output_format: str          # pdf | docx (기본 docx — D4)
    status: str                 # active | deleted (soft-delete)
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class GenerateResult:
    """런타임 생성 결과 DTO (추출기 ComposeResult 동형 — D8)."""

    file_id: str
    filename: str
    section_count: int
    missing_sections: list = field(default_factory=list)  # 재시도 후에도 누락 (D2)
    used_evidence: bool = False                           # 상류 워커 근거 사용 여부
