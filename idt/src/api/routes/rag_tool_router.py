"""RAG Tool Router: RAG 도구 설정에 필요한 메타데이터 조회 API."""
import uuid as _uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.domain.auth.entities import User, UserRole
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/rag-tools", tags=["RAG Tools"])


# ── Response Schemas ──────────────────────────────────────────────

class CollectionInfo(BaseModel):
    name: str
    display_name: str
    vectors_count: int | None = None
    scope: str | None = None


class CollectionsResponse(BaseModel):
    collections: list[CollectionInfo]


class MetadataKeyInfo(BaseModel):
    key: str
    sample_values: list[str]
    value_count: int


class MetadataKeysResponse(BaseModel):
    keys: list[MetadataKeyInfo]


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_qdrant_client():
    raise NotImplementedError


def get_collection_aliases():
    return {}


def get_collection_permission_service():
    raise NotImplementedError


# ── 엔드포인트 ────────────────────────────────────────────────────


@router.get("/collections", response_model=CollectionsResponse)
async def list_collections(
    current_user: User = Depends(get_current_user),
    qdrant_client=Depends(get_qdrant_client),
    aliases: dict = Depends(get_collection_aliases),
    perm_service=Depends(get_collection_permission_service),
):
    """사용 가능한 Qdrant 컬렉션 목록 조회 (권한 필터 적용)."""
    request_id = str(_uuid.uuid4())
    result = await qdrant_client.get_collections()

    is_admin = current_user.role == UserRole.ADMIN
    accessible: set[str] = set()
    if not is_admin:
        accessible = await perm_service.get_accessible_collection_names(
            current_user, request_id
        )

    collections: list[CollectionInfo] = []
    for c in result.collections:
        if not is_admin and accessible and c.name not in accessible:
            continue
        perm = await perm_service.find_permission(c.name, request_id)
        collections.append(
            CollectionInfo(
                name=c.name,
                display_name=aliases.get(c.name, c.name),
                vectors_count=getattr(c, "vectors_count", None),
                scope=perm.scope.value if perm else None,
            )
        )

    return CollectionsResponse(collections=collections)


@router.get("/metadata-keys", response_model=MetadataKeysResponse)
async def list_metadata_keys(
    collection_name: str | None = Query(None),
    qdrant_client=Depends(get_qdrant_client),
):
    """필터링 가능한 메타데이터 키 + 샘플 값 조회."""
    target_collection = collection_name or "documents"

    records, _ = await qdrant_client.scroll(
        collection_name=target_collection,
        limit=100,
        with_vectors=False,
    )

    key_values: dict[str, set[str]] = {}
    for record in records:
        if not record.payload:
            continue
        for k, v in record.payload.items():
            if k == "content":
                continue
            key_values.setdefault(k, set()).add(str(v))

    return MetadataKeysResponse(
        keys=[
            MetadataKeyInfo(
                key=k,
                sample_values=sorted(list(vals))[:10],
                value_count=len(vals),
            )
            for k, vals in sorted(key_values.items())
        ]
    )
