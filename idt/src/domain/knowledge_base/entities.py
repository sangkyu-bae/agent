"""Knowledge Base domain entity.

논리 지식베이스 — 물리 컬렉션과 분리된 payload 필터 단위 (knowledge-base-scoping Design §5.1).
"""
from dataclasses import dataclass
from datetime import datetime

from src.domain.collection.permission_schemas import CollectionScope


@dataclass
class KnowledgeBase:
    name: str
    owner_id: int
    scope: CollectionScope
    collection_name: str
    description: str | None = None
    department_id: str | None = None
    id: str | None = None  # kb_id (UUID v4) — Qdrant/ES payload 필터 키
    status: str = "active"
    # clause-aware-chunking (Design D5): opt-in + late-binding 오버라이드.
    #   NULL 오버라이드 = 업로드 시점 프로파일 값 사용 / 값 = 사용자 고정.
    use_clause_chunking: bool = False
    chunking_profile_id: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    # kb-custom-chunking (Design D1): 독립 opt-in — 조항 청킹과 상호배타(앱 검증).
    #   custom_chunking_config = 전략/파라미터/경계규칙 JSON (저장 형식 그대로 보관,
    #   파싱·검증은 domain custom_chunking 모듈).
    use_custom_chunking: bool = False
    custom_chunking_config: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
