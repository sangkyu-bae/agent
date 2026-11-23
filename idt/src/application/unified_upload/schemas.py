from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class UploadChunkingConfig:
    """업로드 시 사용할 청킹 전략 지정 (clause-aware-chunking Design D10).

    strategy/params는 ChunkingStrategyFactory에 그대로 위임되고,
    display는 document_metadata/응답 기록용이다.
    """
    strategy: str
    params: dict = field(default_factory=dict)
    display: dict = field(default_factory=dict)


@dataclass(frozen=True)
class UnifiedUploadRequest:
    file_bytes: bytes
    filename: str
    user_id: str
    collection_name: str
    child_chunk_size: int = 500
    child_chunk_overlap: int = 50
    # 청크 payload에 추가 주입할 메타데이터 (Qdrant + ES 공통).
    # 고정 키(document_id/user_id/collection_name)가 항상 우선한다.
    extra_metadata: dict[str, str] = field(default_factory=dict)
    # None이면 기존 parent_child 하드코딩 경로, 지정 시 해당 전략 사용 (Design D10).
    chunking_config: "UploadChunkingConfig | None" = None
    # document-revision Design §3.3: document_metadata 신규 행의 계보 필드.
    #   청크 payload 에는 쓰지 않는다(revision_status 부재 = active).
    file_hash: str | None = None
    lineage_id: str | None = None
    version_no: int = 1
    version_label: str | None = None
    effective_date: date | None = None


@dataclass
class QdrantStoreResult:
    stored_ids: list[str]
    embedding_model: str
    error: str | None = None


@dataclass
class EsStoreResult:
    indexed_count: int
    error: str | None = None


@dataclass
class UnifiedUploadResult:
    document_id: str
    filename: str
    total_pages: int
    chunk_count: int
    collection_name: str
    qdrant: QdrantStoreResult
    es: EsStoreResult
    chunking_config: dict
    status: str  # "completed" | "partial" | "failed"
