"""graph_rag 도메인 포트.

Design Ref: graph-rag-foundation §3.1·§9.3 — 구현은 infrastructure/graph_rag/.
module-2 설정·저장소, module-3 적재, module-4 판정·검토. 검색은 module-5.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.graph_rag.extraction import (
    ChunkGraphWrite,
    ChunkUnit,
    EntityWrite,
    ExtractionContext,
    ExtractionJob,
    ExtractionResult,
    JobCounters,
    JobStatus,
    Mention,
)
from src.domain.graph_rag.resolution import (
    Candidate,
    ChooserVerdict,
    ResolutionDecision,
    ReviewStatus,
)
from src.domain.graph_rag.topic import (
    DocumentTopic,
    Topic,
    TopicLevel,
    TopicProposal,
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

    # ── module-4: 판정·검토 ────────────────────────────────────────────────
    @abstractmethod
    async def find_candidates(
        self,
        scope_key: str,
        normalized_name: str,
        embedding: list[float] | None,
        limit: int,
    ) -> list[Candidate]:
        """정규화 이름·별칭 정확 일치 + 이름 벡터 상위 후보(유사도 하한 적용)."""

    @abstractmethod
    async def reassign_decision(self, decision_id: str, to_entity_id: str) -> None:
        """판정 하나에 붙은 언급·관계 끝점을 다른 엔티티로 옮긴다(검토 거절)."""

    @abstractmethod
    async def create_entity(self, entity: EntityWrite) -> None:
        """검토 거절(분리)로 새 엔티티를 만든다."""

    @abstractmethod
    async def delete_entity_if_orphan(self, entity_id: str) -> bool:
        """언급이 하나도 남지 않으면 엔티티·별칭을 지운다."""

    # ── module-4b: 주제 ────────────────────────────────────────────────────
    @abstractmethod
    async def set_document_topics(self, document_id: str, topic_ids: list[str]) -> None:
        """문서의 모든 Chunk 노드 topic_ids 를 바꾼다(검색 범위 필터 복사본)."""


class TopicRepositoryPort(ABC):
    """V090 graph_topic — 앱 수명 싱글턴, 호출마다 짧은 세션."""

    @abstractmethod
    async def list(
        self,
        request_id: str,
        *,
        level: TopicLevel | None = None,
        parent_id: str | None = None,
        include_retired: bool = False,
    ) -> list[Topic]: ...

    @abstractmethod
    async def get(self, topic_id: str, request_id: str) -> Topic | None: ...

    @abstractmethod
    async def find_by_name(
        self, parent_key: str, normalized_name: str, request_id: str
    ) -> Topic | None: ...

    @abstractmethod
    async def create(self, topic: Topic, request_id: str) -> Topic:
        """같은 (parent_key, normalized_name) 이 있으면 GraphTopicDuplicateError."""

    @abstractmethod
    async def update(self, topic: Topic, request_id: str) -> Topic:
        """이름·설명·상태 변경. 이름 충돌은 GraphTopicDuplicateError."""


class DocumentTopicStorePort(ABC):
    """V091 graph_document_topic."""

    @abstractmethod
    async def list_for_document(
        self, document_id: str, request_id: str
    ) -> list[DocumentTopic]: ...

    @abstractmethod
    async def replace(
        self, document_id: str, links: list[DocumentTopic], request_id: str
    ) -> None:
        """문서의 연결을 통째로 바꾼다(재분류)."""

    @abstractmethod
    async def move(
        self, decision_id: str, to_topic_id: str, request_id: str
    ) -> str | None:
        """판정 하나의 연결을 다른 주제로 옮긴다(검토 거절). 옮긴 문서 id."""

    @abstractmethod
    async def count_documents(
        self, topic_ids: list[str], request_id: str
    ) -> dict[str, int]: ...


class TopicProposerPort(ABC):
    """문서 앞부분 → 주제 제안(LLM)."""

    @abstractmethod
    async def propose(self, excerpt: str, request_id: str) -> TopicProposal: ...


class EntityChooserPort(ABC):
    """후보 중 같은 대상 고르기 — Jev(확률) 또는 LLM(라벨·확신도)."""

    @abstractmethod
    async def choose(
        self,
        mention: Mention,
        context: str,
        candidates: dict[str, Candidate],
        request_id: str,
    ) -> ChooserVerdict: ...


class EntityEmbedderPort(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class DecisionStorePort(ABC):
    """V089 판정 기록 — 앱 수명 싱글턴, 호출마다 짧은 세션."""

    @abstractmethod
    async def upsert_many(
        self, decisions: list[ResolutionDecision], request_id: str
    ) -> None: ...

    @abstractmethod
    async def get(
        self, decision_id: str, request_id: str
    ) -> ResolutionDecision | None: ...

    @abstractmethod
    async def list_by_review_status(
        self, status: ReviewStatus, limit: int, offset: int, request_id: str
    ) -> tuple[list[ResolutionDecision], int]: ...

    @abstractmethod
    async def mark_reviewed(
        self,
        decision_id: str,
        status: ReviewStatus,
        reviewer: str,
        note: str | None,
        entity_id: str,
        request_id: str,
    ) -> None: ...


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
