"""원문 뷰어 값 객체 (Design §3.1). 외부 의존 없음."""
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Optional


class OriginalKind(StrEnum):
    """원본 뷰어가 렌더할 수 있는 형식. wire 값 — 변경은 프론트 계약 변경이다."""

    PDF = "pdf"
    DOCX = "docx"


@dataclass(frozen=True)
class Passage:
    """한 실행에서 한 문서로 검색된 청크 1개."""

    chunk_id: str
    parent_id: Optional[str]
    page: Optional[int]
    rank: int
    excerpt: str


@dataclass(frozen=True)
class ViewerRef:
    """문서 칩에 덧붙는 뷰어 진입 정보. original=None 이면 텍스트 뷰어."""

    document_id: str
    kb_id: str
    original: Optional[OriginalKind]
    passages: tuple[Passage, ...]

    def to_payload(self) -> dict[str, Any]:
        """프론트 `SourceViewerRef` 형태 (Design §3.3). rank 는 순서로 표현해 싣지 않는다."""
        return {
            "document_id": self.document_id,
            "kb_id": self.kb_id,
            "original": self.original.value if self.original else None,
            "passages": [
                {
                    "chunk_id": p.chunk_id,
                    "parent_id": p.parent_id,
                    "page": p.page,
                    "excerpt": p.excerpt,
                }
                for p in self.passages
            ],
        }
