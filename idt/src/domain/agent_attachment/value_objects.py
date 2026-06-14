"""Agent 첨부 도메인 값 객체 (ws-agent-excel-attachment Design §3.1).

⚠️ 외부 의존(DB·LangChain·파일 I/O) 금지 — 순수 값/규칙만.
"""
from dataclasses import dataclass
from enum import Enum


class AttachmentType(str, Enum):
    """첨부 타입.

    확장 지점: CSV 등 신규 타입은 여기에 멤버를 추가하고
    AttachmentPolicy.ALLOWED_EXT에 확장자 매핑만 더하면 된다 (OCP).
    """

    EXCEL = "excel"


@dataclass(frozen=True)
class AttachmentRef:
    """업로드된 첨부에 대한 불변 참조 (발급 결과)."""

    file_id: str
    type: AttachmentType
    filename: str
    size: int


@dataclass(frozen=True)
class StoredAttachment:
    """저장소에 영속화된 첨부 — 소유자/경로 포함.

    file_path는 서버 파일시스템 경로로, 분석 노드(ExcelAnalysisWorkflow)가 소비한다.
    """

    file_id: str
    type: AttachmentType
    filename: str
    size: int
    owner_user_id: str
    file_path: str
