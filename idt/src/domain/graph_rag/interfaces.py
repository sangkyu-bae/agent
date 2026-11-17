"""graph_rag 도메인 포트 (module-2 범위).

Design Ref: graph-rag-foundation §3.1·§9.3 — 구현은 infrastructure/graph_rag/.
GraphStorePort 는 module-3~5 에서 쓰기·탐색 메서드가 추가된다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.graph_rag.extraction import (
    ChunkGraphWrite,
    ChunkUnit,
    ExtractionContext,
    ExtractionJob,
    ExtractionResult,
    JobCounters,
    JobStatus,
)
from src.domain.graph_rag.value_objects import GraphRagSettings, StageChange


class GraphRagSettingsRepositoryPort(ABC):
    @abstractmethod
    async def get(self, request_id: str) -> GraphRagSettings: ...

    @abstractmethod
    async def update(
        self, settings: GraphRagSettings, request_id: str
    ) -> GraphRagSettings: ...


class StageChangeRepositoryPort(ABC):
    @abstractmethod
    async def add(self, change: StageChange, request_id: str) -> None: ...

    @abstractmethod
    async def list_recent(self, limit: int, request_id: str) -> list[StageChange]: ...


class GraphSettingsReaderPort(ABC):
    """요청 세션 밖(검색·노출 판단)에서 읽는 설정. 실패 시 닫힌 기본값을 돌려준다."""

    @abstractmethod
    async def get(self) -> GraphRagSettings: ...

    @abstractmethod
    def invalidate(self) -> None: ...


class EvalEvidenceVerifierPort(ABC):
    """general 전환 근거(RAGAS 그래프 off/on 실행 2건) 검증 — module-7 에서 실구현."""

    @abstractmethod
    async def is_valid(
        self, baseline_run_id: str | None, graph_run_id: str | None, request_id: str
    ) -> bool: ...


class GraphStorePort(ABC):
    @abstractmethod
    async def ping(self) -> None:
        """연결 확인. 실패 시 GraphBackendUnavailableError."""

    @abstractmethod
    async def counts(self) -> tuple[int, int]:
        """(노드 수, 관계 수)."""

    @abstractmethod
    async def ensure_schema(self, embedding_dimensions: int) -> None:
        """제약·인덱스 멱등 생성.

        벡터 인덱스 차원 불일치면 GraphEmbeddingDimMismatchError.
        """

    @abstractmethod
    async def aclose(self) -> None: ...

    # ── module-3: 적재 ──────────────────────────────────────────────────────
    @abstractmethod
    async def extracted_chunk_ids(self, document_id: str, version: str) -> set[str]:
        """같은 추출기 버전으로 이미 저장된 청크 id (resume 용)."""

    @abstractmethod
    async def delete_document(self, document_id: str) -> None:
        """문서의 청크·언급·관계 근거 삭제 + 고아 엔티티 정리 (rebuild·삭제 훅)."""

    @abstractmethod
    async def find_entity_id(
        self, scope_key: str, normalized_name: str, type_: str
    ) -> str | None:
        """정규화 이름·타입 정확 일치 엔티티 id (module-3 임시 판정)."""

    @abstractmethod
    async def write_chunk_graph(self, write: ChunkGraphWrite) -> None:
        """청크 1개의 엔티티·언급·관계를 한 트랜잭션으로 저장."""


class ExtractionJobStorePort(ABC):
    """앱 수명 싱글턴 — 호출마다 짧은 독립 세션(SessionScoped 선례)."""

    @abstractmethod
    async def create(self, job: ExtractionJob, request_id: str) -> ExtractionJob: ...

    @abstractmethod
    async def get(self, job_id: str, request_id: str) -> ExtractionJob | None: ...

    @abstractmethod
    async def find_active(
        self, document_id: str, request_id: str
    ) -> ExtractionJob | None: ...

    @abstractmethod
    async def latest_by_documents(
        self, document_ids: list[str], request_id: str
    ) -> dict[str, ExtractionJob]: ...

    @abstractmethod
    async def mark_processing(
        self, job_id: str, total_chunks: int, request_id: str
    ) -> None: ...

    @abstractmethod
    async def save_progress(
        self, job_id: str, counters: JobCounters, request_id: str
    ) -> None: ...

    @abstractmethod
    async def finish(
        self,
        job_id: str,
        status: JobStatus,
        counters: JobCounters,
        error: str | None,
        request_id: str,
    ) -> None: ...

    @abstractmethod
    async def fail_interrupted(self, request_id: str) -> int:
        """기동 시 pending·processing 잡을 failed(interrupted)로 — 바뀐 수."""


class ChunkSourcePort(ABC):
    @abstractmethod
    async def list_units(
        self, document_id: str, request_id: str
    ) -> list[ChunkUnit]: ...


class GraphExtractorPort(ABC):
    """청크 1개 → 언급·관계 초안 (규칙 추출기·LLM 추출기 공통)."""

    @abstractmethod
    async def extract(
        self, unit: ChunkUnit, context: ExtractionContext
    ) -> ExtractionResult: ...
