"""document_extractor 도메인 스키마 (Design §2-1).

⚠️ 외부 의존(DB·LangChain·파일 I/O) 금지 — 순수 값/규칙만.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

SlotType = Literal["value", "generated"]

# 토큰 안전(ASCII) — {{key}} 치환의 단일 규칙 출처
SLOT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,49}$")

TEMPLATE_STATUS_ACTIVE = "active"
TEMPLATE_STATUS_DELETED = "deleted"


@dataclass(frozen=True)
class TemplateSlot:
    """자동화 슬롯 정의. anchor(`{{key}}`)가 html_skeleton 치환 지점이다."""

    key: str
    label: str
    slot_type: SlotType
    description: str = ""
    fill_hint: str = ""
    sample_value: str = ""

    @property
    def anchor(self) -> str:
        """html_skeleton 내 치환 토큰 — 예: "{{loan_amount}}"."""
        return "{{" + self.key + "}}"


@dataclass
class DocumentTemplate:
    """그 에이전트·그 도구 전용 문서 템플릿 (공유/fork 없음 — Plan 관심사 분리 ②)."""

    id: str
    agent_id: str
    worker_id: str
    name: str
    html_skeleton: str          # {{key}} 토큰화된 HTML (방식 A)
    slots: list[TemplateSlot]
    source_file_ref: str        # 영구 보관 원본 경로 (D3)
    source_format: str          # "pdf" | "docx"
    status: str                 # active | deleted (soft-delete)
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SuggestedSlots:
    """빌드타임 추출/재추천 결과 DTO (stateless)."""

    slots: list[TemplateSlot] = field(default_factory=list)
