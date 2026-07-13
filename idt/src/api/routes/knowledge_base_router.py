"""Knowledge Base Router: 지식베이스 CRUD + 지정 업로드 API (knowledge-base-scoping Design §7.1)."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from src.application.knowledge_base.list_documents_use_case import (
    ListKbDocumentsUseCase,
)
from src.application.knowledge_base.upload_use_case import (
    KnowledgeBaseUploadUseCase,
)
from src.application.knowledge_base.use_case import KnowledgeBaseUseCase
from src.application.section_summary.query_use_case import (
    SectionSummaryQueryUseCase,
)
from src.application.section_summary.schemas import (
    SectionSummaryJobStatus,
    SectionSummaryRetryNotAllowedError,
)
from src.domain.auth.entities import User
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["KnowledgeBases"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_knowledge_base_use_case() -> KnowledgeBaseUseCase:
    raise NotImplementedError


def get_kb_upload_use_case() -> KnowledgeBaseUploadUseCase:
    raise NotImplementedError


def get_section_summary_query_use_case() -> SectionSummaryQueryUseCase:
    raise NotImplementedError


def get_list_kb_documents_use_case() -> "ListKbDocumentsUseCase":
    raise NotImplementedError


# ── Request / Response Schemas ───────────────────────────────────

class CreateKnowledgeBaseBody(BaseModel):
    name: str
    description: str | None = None
    scope: str = "PERSONAL"
    department_id: str | None = None
    collection_name: str
    # clause-aware-chunking (Design §8.3): opt-in + late-binding 오버라이드
    use_clause_chunking: bool = False
    chunking_profile_id: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None


class KbInfoResponse(BaseModel):
    kb_id: str
    name: str
    description: str | None
    scope: str
    department_id: str | None
    collection_name: str
    owner_id: int
    use_clause_chunking: bool = False
    chunking_profile_id: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    created_at: datetime | None


class KbListResponse(BaseModel):
    knowledge_bases: list[KbInfoResponse]
    total: int


class KbCreateResponse(BaseModel):
    kb_id: str
    name: str
    scope: str
    collection_name: str
    message: str


class KbMessageResponse(BaseModel):
    kb_id: str
    message: str


class KbStoreResultResponse(BaseModel):
    status: str
    error: str | None = None


class KbSectionSummaryLaunchResponse(BaseModel):
    """업로드 응답의 섹션 요약 잡 킥오프 정보 (card-section-summary D15)."""

    job_id: str
    status: str


class KbUploadResponse(BaseModel):
    kb_id: str
    kb_name: str
    collection_name: str
    document_id: str
    filename: str
    total_pages: int
    chunk_count: int
    chunking_strategy: str
    qdrant: KbStoreResultResponse
    es: KbStoreResultResponse
    status: str
    # 요약 비활성 프로파일/기존 경로는 null (card-section-summary D15)
    section_summary: KbSectionSummaryLaunchResponse | None = None


class KbDocumentInfoResponse(BaseModel):
    """지식베이스 문서 목록 항목 (kb-management-ui §4.5)."""

    document_id: str
    filename: str
    chunk_count: int
    chunking_strategy: str
    created_at: datetime | None


class KbDocumentListResponse(BaseModel):
    kb_id: str
    kb_name: str
    documents: list[KbDocumentInfoResponse]
    total: int
    offset: int
    limit: int


class SectionSummaryStatusResponse(BaseModel):
    """섹션 요약 잡 상태 (card-section-summary §7.2)."""

    job_id: str
    document_id: str
    status: str
    total_sections: int | None
    done_sections: int
    failed_sections: int
    is_stale: bool
    error: str | None
    created_at: datetime | None
    updated_at: datetime | None


def _to_kb_info(kb: KnowledgeBase) -> KbInfoResponse:
    return KbInfoResponse(
        kb_id=kb.id,
        name=kb.name,
        description=kb.description,
        scope=kb.scope.value,
        department_id=kb.department_id,
        collection_name=kb.collection_name,
        owner_id=kb.owner_id,
        use_clause_chunking=kb.use_clause_chunking,
        chunking_profile_id=kb.chunking_profile_id,
        chunk_size=kb.chunk_size,
        chunk_overlap=kb.chunk_overlap,
        created_at=kb.created_at,
    )


def _raise_http(e: Exception) -> None:
    """UseCase 예외 → HTTP 상태코드 매핑 (collection_router 규약과 동일)."""
    if isinstance(e, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    msg = str(e)
    if "not found" in msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "already exists" in msg:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
    )


# ── Endpoints ─────────────────────────────────────────────────────


@router.post("", status_code=201, response_model=KbCreateResponse)
async def create_knowledge_base(
    body: CreateKnowledgeBaseBody,
    current_user: User = Depends(get_current_user),
    use_case: KnowledgeBaseUseCase = Depends(get_knowledge_base_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        scope = CollectionScope(body.scope)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid scope: '{body.scope}'",
        )
    try:
        kb = await use_case.create(
            user=current_user,
            name=body.name,
            collection_name=body.collection_name,
            scope=scope,
            department_id=body.department_id,
            description=body.description,
            request_id=request_id,
            use_clause_chunking=body.use_clause_chunking,
            chunking_profile_id=body.chunking_profile_id,
            chunk_size=body.chunk_size,
            chunk_overlap=body.chunk_overlap,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        # create는 404 없음 — 대상 컬렉션 미존재도 요청 본문 문제(422)로 취급 (Design §7.1)
        msg = str(e)
        if "already exists" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
        )
    return KbCreateResponse(
        kb_id=kb.id,
        name=kb.name,
        scope=kb.scope.value,
        collection_name=kb.collection_name,
        message="Knowledge base created successfully",
    )


@router.get("", response_model=KbListResponse)
async def list_knowledge_bases(
    current_user: User = Depends(get_current_user),
    use_case: KnowledgeBaseUseCase = Depends(get_knowledge_base_use_case),
):
    request_id = str(uuid.uuid4())
    result = await use_case.list(current_user, request_id)
    return KbListResponse(
        knowledge_bases=[_to_kb_info(kb) for kb in result],
        total=len(result),
    )


@router.get("/{kb_id}", response_model=KbInfoResponse)
async def get_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    use_case: KnowledgeBaseUseCase = Depends(get_knowledge_base_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        kb = await use_case.get(kb_id, current_user, request_id)
    except (PermissionError, ValueError) as e:
        _raise_http(e)
    return _to_kb_info(kb)


@router.delete("/{kb_id}", response_model=KbMessageResponse)
async def delete_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    use_case: KnowledgeBaseUseCase = Depends(get_knowledge_base_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        await use_case.delete(kb_id, current_user, request_id)
    except (PermissionError, ValueError) as e:
        _raise_http(e)
    return KbMessageResponse(
        kb_id=kb_id,
        message=(
            "Knowledge base deleted. "
            "Stored vectors remain until cleanup."
        ),
    )


@router.get(
    "/{kb_id}/documents",
    response_model=KbDocumentListResponse,
    description=(
        "지식베이스에 속한 문서 목록을 조회한다 (kb-management-ui D1). "
        "kb_id payload로 기록된 문서만 반환하며, 같은 물리 컬렉션의 "
        "다른 KB 문서는 포함되지 않는다. V047 이전 업로드 문서(kb_id NULL)는 "
        "목록에 나타나지 않는다 (D4 알려진 한계)."
    ),
)
async def list_kb_documents(
    kb_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    use_case: ListKbDocumentsUseCase = Depends(get_list_kb_documents_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        result = await use_case.execute(
            kb_id, current_user, request_id, offset=offset, limit=limit
        )
    except (PermissionError, ValueError) as e:
        _raise_http(e)
    return KbDocumentListResponse(
        kb_id=result.kb_id,
        kb_name=result.kb_name,
        documents=[
            KbDocumentInfoResponse(
                document_id=d.document_id,
                filename=d.filename,
                chunk_count=d.chunk_count,
                chunking_strategy=d.chunk_strategy,
                created_at=d.created_at,
            )
            for d in result.documents
        ],
        total=result.total,
        offset=result.offset,
        limit=result.limit,
    )


@router.post(
    "/{kb_id}/documents",
    response_model=KbUploadResponse,
    description=(
        "지식베이스에 문서를 업로드한다. use_clause_chunking이 켜진 KB는 청킹 설정을 "
        "KB 레코드/프로파일에서 결정하므로 child_chunk_size·child_chunk_overlap "
        "Query 파라미터는 무시된다 (clause-aware-chunking Design D6). "
        "적용된 전략은 응답 chunking_strategy로 확인한다."
    ),
)
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    child_chunk_size: int = Query(500, ge=100, le=4000),
    child_chunk_overlap: int = Query(50, ge=0, le=500),
    current_user: User = Depends(get_current_user),
    use_case: KnowledgeBaseUploadUseCase = Depends(get_kb_upload_use_case),
):
    request_id = str(uuid.uuid4())
    file_bytes = await file.read()
    filename = file.filename or "unknown.pdf"
    try:
        result, kb, summary_launch = await use_case.execute(
            kb_id,
            current_user,
            file_bytes,
            filename,
            request_id,
            child_chunk_size=child_chunk_size,
            child_chunk_overlap=child_chunk_overlap,
        )
    except (PermissionError, ValueError) as e:
        _raise_http(e)
    return KbUploadResponse(
        kb_id=kb.id,
        kb_name=kb.name,
        collection_name=kb.collection_name,
        document_id=result.document_id,
        filename=result.filename,
        total_pages=result.total_pages,
        chunk_count=result.chunk_count,
        chunking_strategy=result.chunking_config.get("strategy", "parent_child"),
        qdrant=KbStoreResultResponse(
            status="success" if not result.qdrant.error else "failed",
            error=result.qdrant.error,
        ),
        es=KbStoreResultResponse(
            status="success" if not result.es.error else "failed",
            error=result.es.error,
        ),
        status=result.status,
        section_summary=(
            KbSectionSummaryLaunchResponse(
                job_id=summary_launch.job_id, status=summary_launch.status
            )
            if summary_launch is not None
            else None
        ),
    )


def _to_summary_status(
    job_status: SectionSummaryJobStatus,
) -> SectionSummaryStatusResponse:
    return SectionSummaryStatusResponse(
        job_id=job_status.job_id,
        document_id=job_status.document_id,
        status=job_status.status,
        total_sections=job_status.total_sections,
        done_sections=job_status.done_sections,
        failed_sections=job_status.failed_sections,
        is_stale=job_status.is_stale,
        error=job_status.error,
        created_at=job_status.created_at,
        updated_at=job_status.updated_at,
    )


@router.get(
    "/{kb_id}/documents/{document_id}/section-summary",
    response_model=SectionSummaryStatusResponse,
    description=(
        "문서의 섹션 요약 잡 상태(처리중/완료/실패, 진행률)를 조회한다. "
        "completed는 섹션 전량 + 문서 단위 요약 생성까지 성공을 의미한다 "
        "(document-summary-routing D3). "
        "요약 비활성 프로파일로 업로드된 문서는 404 (card-section-summary §7.2)."
    ),
)
async def get_section_summary_status(
    kb_id: str,
    document_id: str,
    current_user: User = Depends(get_current_user),
    use_case: SectionSummaryQueryUseCase = Depends(
        get_section_summary_query_use_case
    ),
):
    request_id = str(uuid.uuid4())
    try:
        job_status = await use_case.get_status(
            kb_id, document_id, current_user, request_id
        )
    except (PermissionError, ValueError) as e:
        _raise_http(e)
    return _to_summary_status(job_status)


@router.post(
    "/{kb_id}/documents/{document_id}/section-summary/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SectionSummaryStatusResponse,
    description=(
        "실패했거나 stale(서버 재시작 고아)한 섹션 요약 잡을 재실행한다. "
        "완료된 섹션은 재처리하지 않고 문서 단위 요약은 재생성한다 "
        "(card-section-summary §7.3, document-summary-routing D4)."
    ),
)
async def retry_section_summary(
    kb_id: str,
    document_id: str,
    current_user: User = Depends(get_current_user),
    use_case: SectionSummaryQueryUseCase = Depends(
        get_section_summary_query_use_case
    ),
):
    request_id = str(uuid.uuid4())
    try:
        job_status = await use_case.retry(
            kb_id, document_id, current_user, request_id
        )
    except SectionSummaryRetryNotAllowedError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        )
    except (PermissionError, ValueError) as e:
        _raise_http(e)
    return _to_summary_status(job_status)
