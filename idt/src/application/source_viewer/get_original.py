"""원본 파일 조회 (Design §4.2, §7).

권한은 기존 KbDocumentGuard 를 그대로 쓴다 — KB 읽기 권한 + 문서의 KB 소속.
RAG 검색도 같은 can_read 규칙을 지나므로 칩에 나온 문서와 판정이 같다.
순서: 권한(403/404) → 형식(415, 디스크를 읽지 않음) → 원본(404).
"""
from dataclasses import dataclass
from typing import Any, Protocol

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.source_viewer.exceptions import (
    OriginalNotAvailableError,
    UnsupportedOriginalError,
)
from src.domain.source_viewer.models import OriginalKind
from src.domain.source_viewer.policy import PassagePolicy
from src.domain.source_viewer.ports import OriginalStorePort

_MEDIA_TYPES = {
    OriginalKind.PDF: "application/pdf",
    OriginalKind.DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
}


class _DocumentGuard(Protocol):
    """KbDocumentGuard.ensure 의 모양 — application 계층끼리라도 구현을 직접 묶지 않는다."""

    async def ensure(self, kb_id: str, document_id: str, user: Any, request_id: str) -> Any: ...


@dataclass(frozen=True)
class OriginalFile:
    content: bytes
    media_type: str
    filename: str


class GetOriginalUseCase:
    def __init__(
        self, guard: _DocumentGuard, store: OriginalStorePort, logger: LoggerInterface,
    ) -> None:
        self._guard = guard
        self._store = store
        self._logger = logger

    async def execute(
        self, kb_id: str, document_id: str, user: Any, request_id: str,
    ) -> OriginalFile:
        ctx = await self._guard.ensure(kb_id, document_id, user, request_id)
        kind = PassagePolicy.original_kind(ctx.filename)
        if kind is None:
            raise UnsupportedOriginalError()
        content = await self._read(document_id, request_id)
        return OriginalFile(
            content=content, media_type=_MEDIA_TYPES[kind], filename=ctx.filename,
        )

    async def _read(self, document_id: str, request_id: str) -> bytes:
        try:
            content = await self._store.open(document_id)
        except ValueError:
            # UUID 가 아닌 옛 document_id — 보관 대상이 될 수 없었던 문서다.
            content = None
        if content is None:
            self._logger.info(
                "source viewer original not available",
                request_id=request_id, document_id=document_id,
            )
            raise OriginalNotAvailableError()
        return content
