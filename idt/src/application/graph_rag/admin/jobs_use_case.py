"""관리자 추출 잡 유스케이스 — 문서별 상태 조회·실행·잡 상세 (Design §4.1, FR-16).

오류는 라우터가 Design §6.1 코드로 매핑한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from src.domain.graph_rag.exceptions import (
    GraphBackendUnavailableError,
    GraphRagError,
    GraphStageOffError,
)
from src.domain.graph_rag.extraction import (
    DocumentEligibilityPolicy,
    ExtractionJob,
    JobMode,
    TriggerSource,
)
from src.domain.graph_rag.interfaces import (
    ExtractionJobStorePort,
    GraphSettingsReaderPort,
)
from src.domain.graph_rag.value_objects import RolloutStage
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mysql.schemas import MySQLPaginationParams


class GraphJobBusyError(GraphRagError):
    code = "GRAPH_JOB_BUSY"


class GraphModelMissingError(GraphRagError):
    code = "GRAPH_EXTRACTION_MODEL_MISSING"


class DocumentNotFoundError(GraphRagError):
    code = "DOCUMENT_NOT_FOUND"


class GraphUnsupportedDocumentError(GraphRagError):
    """표 데이터(엑셀·CSV) 문서 — DocumentEligibilityPolicy (422)."""

    code = "GRAPH_UNSUPPORTED_DOCUMENT"


class _Documents(Protocol):
    async def find_by_document_id(self, document_id: str, request_id: str) -> Any: ...

    async def find_by_kb_id(
        self, kb_id: str, request_id: str, pagination: Any = None
    ) -> Any: ...


class _Launcher(Protocol):
    async def launch(self, **kwargs: Any) -> ExtractionJob: ...

    def is_running(self, document_id: str) -> bool: ...


@dataclass(frozen=True)
class DocumentJobRow:
    document_id: str
    filename: str
    chunk_count: int
    job: ExtractionJob | None


class ExtractionJobsUseCase:
    def __init__(
        self,
        *,
        jobs: ExtractionJobStorePort,
        launcher: _Launcher,
        reader: GraphSettingsReaderPort,
        documents: _Documents,
        store_available: Callable[[], bool],
        logger: LoggerInterface,
    ) -> None:
        self._jobs = jobs
        self._launcher = launcher
        self._reader = reader
        self._documents = documents
        self._store_available = store_available
        self._logger = logger

    async def trigger(
        self, document_id: str, mode: JobMode, *, actor_id: str, request_id: str
    ) -> ExtractionJob:
        await self._check_ready()
        doc = await self._documents.find_by_document_id(document_id, request_id)
        if doc is None:
            raise DocumentNotFoundError(f"document not found: {document_id}")
        if not DocumentEligibilityPolicy.is_extractable(doc.filename):
            raise GraphUnsupportedDocumentError(
                "spreadsheet documents are not extracted into the graph"
            )
        active = await self._jobs.find_active(document_id, request_id)
        if active is not None or self._launcher.is_running(document_id):
            raise GraphJobBusyError("extraction already running for this document")
        return await self._launcher.launch(
            document_id=document_id,
            kb_id=getattr(doc, "kb_id", None),
            collection_name=doc.collection_name,
            mode=mode,
            trigger=TriggerSource.ADMIN,
            requested_by=actor_id,
            request_id=request_id,
        )

    async def _check_ready(self) -> None:
        settings = await self._reader.get()
        if settings.rollout_stage is RolloutStage.OFF:
            raise GraphStageOffError("graph rag is off")
        if not settings.extraction_llm_model_id:
            raise GraphModelMissingError("set extraction llm model first")
        if not self._store_available():
            raise GraphBackendUnavailableError("graph backend not configured")

    async def get(self, job_id: str, request_id: str) -> ExtractionJob | None:
        return await self._jobs.get(job_id, request_id)

    async def list_kb_documents(
        self, kb_id: str, request_id: str, *, limit: int = 200, offset: int = 0
    ) -> tuple[list[DocumentJobRow], int]:
        """KB 문서(최신순) + 문서별 최근 잡. 관리자 전용이라 KB 권한 검사는 없다."""
        page = await self._documents.find_by_kb_id(
            kb_id, request_id, MySQLPaginationParams(limit=limit, offset=offset)
        )
        return await self.rows_for(list(page.items), request_id), int(page.total)

    async def rows_for(
        self, documents: list[Any], request_id: str
    ) -> list[DocumentJobRow]:
        latest = await self._jobs.latest_by_documents(
            [d.document_id for d in documents], request_id
        )
        return [
            DocumentJobRow(
                document_id=d.document_id,
                filename=d.filename,
                chunk_count=int(getattr(d, "chunk_count", 0) or 0),
                job=latest.get(d.document_id),
            )
            for d in documents
        ]
