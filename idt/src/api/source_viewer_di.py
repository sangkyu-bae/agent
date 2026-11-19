"""source-passage-viewer 조립 — 코어에 끼워 넣는 단일 지점 (Design §2.1, §6, §11.2 #5).

Design Ref: source-passage-viewer §9.2 — graph_rag_di 선례. main.py 는 이 모듈의
접근자 3개(sink·enricher·wire)만 부른다. source_viewer 패키지 import 는 여기와 라우터뿐이다.

- SOURCE_VIEWER_ENABLED=false → 모든 접근자가 None/False, 라우터 미등록(404)
- DOCUMENT_ORIGINAL_STORAGE_DIR 비움 → enricher 만(텍스트 뷰어), 원본 보관·원본 API 없음
- 조립 실패 → warning 1회 후 기능 없음. 앱 기동은 계속된다.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes import source_viewer_router
from src.application.knowledge_base.content_browse_guard import KbDocumentGuard
from src.application.source_viewer.enricher import SourceViewerEnricher
from src.application.source_viewer.get_original import GetOriginalUseCase
from src.application.source_viewer.original_sink import OriginalSink
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.doc_browse.document_metadata_repository import (
    DocumentMetadataRepository,
)
from src.infrastructure.logging import StructuredLogger
from src.infrastructure.source_viewer.local_disk_store import LocalDiskOriginalStore


@dataclass(frozen=True)
class SourceViewerParts:
    enricher: SourceViewerEnricher
    store: Optional[LocalDiskOriginalStore]
    sink: Optional[OriginalSink]


_parts: Optional[SourceViewerParts] = None
_built = False


def build_source_viewer(settings: Any, logger: LoggerInterface) -> Optional[SourceViewerParts]:
    """설정 → 부품. 소비: config.source_viewer_enabled / document_original_storage_dir."""
    if not settings.source_viewer_enabled:
        return None
    try:
        root = (settings.document_original_storage_dir or "").strip()
        store = LocalDiskOriginalStore(root) if root else None
        sink = OriginalSink(store, logger) if store is not None else None
        return SourceViewerParts(
            enricher=SourceViewerEnricher(store, logger), store=store, sink=sink,
        )
    except Exception as e:  # noqa: BLE001 — 부가 기능 조립 실패가 기동을 막으면 안 된다
        logger.warning("source_viewer assembly failed — feature disabled", exception=e)
        return None


def get_source_viewer() -> Optional[SourceViewerParts]:
    """앱 수명 1회 조립 — 요청마다 재시도하지 않는다(prompt_guard 선례)."""
    global _parts, _built
    if not _built:
        from src.config import settings

        _built = True
        _parts = build_source_viewer(settings, StructuredLogger("source_viewer"))
    return _parts


def source_viewer_sink() -> Optional[OriginalSink]:
    parts = get_source_viewer()
    return parts.sink if parts else None


def source_viewer_enricher() -> Optional[SourceViewerEnricher]:
    parts = get_source_viewer()
    return parts.enricher if parts else None


def wire_source_viewer(
    app: FastAPI,
    *,
    kb_uc_factory: Callable[[AsyncSession], Any],
    get_session: Callable[..., Any],
) -> bool:
    """원본 API 라우터 등록. 원본 저장소가 없으면 등록하지 않는다(텍스트 뷰어는 기존 청크 API)."""
    parts = get_source_viewer()
    if parts is None or parts.store is None:
        return False
    store = parts.store
    logger = StructuredLogger("source_viewer.original")

    def use_case_factory(session: AsyncSession = Depends(get_session)) -> GetOriginalUseCase:
        guard = KbDocumentGuard(
            kb_use_case=kb_uc_factory(session),
            document_metadata_repo=DocumentMetadataRepository(session, logger),
            logger=logger,
        )
        return GetOriginalUseCase(guard, store, logger)

    app.dependency_overrides[source_viewer_router.get_original_use_case] = use_case_factory
    app.include_router(source_viewer_router.router)
    return True
