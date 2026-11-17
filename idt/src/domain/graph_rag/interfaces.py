"""graph_rag 도메인 포트 (module-2 범위).

Design Ref: graph-rag-foundation §3.1·§9.3 — 구현은 infrastructure/graph_rag/.
GraphStorePort 는 module-3~5 에서 쓰기·탐색 메서드가 추가된다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

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
