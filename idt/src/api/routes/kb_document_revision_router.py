"""KB 문서 개정 라우터 — document-revision Design §4.1.

#1 사전 점검, #4 이력, #5 되돌리기, #6 사후 연결, #7 메타, #8 재반영, #10 개정 모드.
(#2 업로드·#3 목록·#9 삭제는 knowledge_base_router 의 기존 엔드포인트를 확장했다.)
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from src.api.routes.knowledge_base_router import get_knowledge_base_use_case
from src.application.document_revision.revision_check_use_case import (
    RevisionCheckUseCase,
)
from src.application.document_revision.revision_management_use_case import (
    RevisionManagementUseCase,
)
from src.application.knowledge_base.use_case import KnowledgeBaseUseCase
from src.domain.auth.entities import User
from src.domain.document_revision.errors import (
    DocumentRevisionError,
    RevisionModeNotAvailableError,
)
from src.domain.document_revision.value_objects import RollbackMode
from src.interfaces.dependencies.auth import get_current_user
from src.interfaces.schemas.document_revision import (
    DocumentVersionResponse,
    RevisionCheckResponse,
    revision_error_detail,
)

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["KnowledgeBaseRevision"])


def get_revision_check_use_case() -> RevisionCheckUseCase:
    raise NotImplementedError("DI not configured")


def get_revision_management_use_case() -> RevisionManagementUseCase:
    raise NotImplementedError("DI not configured")


# ── 스키마 ────────────────────────────────────────────────
class DocumentVersionsResponse(BaseModel):
    lineage_id: str
    versions: list[DocumentVersionResponse]


class RollbackRequest(BaseModel):
    mode: RollbackMode


class RollbackResponse(BaseModel):
    restored_document_id: str
    detached_document_id: str | None
    deleted_document_id: str | None
    sync_state: str


class LinkRequest(BaseModel):
    supersedes_document_id: str = Field(..., min_length=1, max_length=64)


class LinkResponse(BaseModel):
    document: DocumentVersionResponse
    sync_state: str


class RevisionMetaRequest(BaseModel):
    version_label: str | None = Field(None, max_length=100)
    effective_date: date | None = None


class RevisionSyncResponse(BaseModel):
    document_id: str
    revision_status: str
    sync_state: str


class RevisionModeRequest(BaseModel):
    revision_mode: str = Field(..., max_length=10)


class RevisionModeResponse(BaseModel):
    kb_id: str
    revision_mode: str


# ── 오류 변환 ─────────────────────────────────────────────
def _raise_http(e: Exception) -> None:
    if isinstance(e, RevisionModeNotAvailableError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=revision_error_detail(e),
        ) from e
    if isinstance(e, DocumentRevisionError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=revision_error_detail(e)
        ) from e
    if isinstance(e, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    msg = str(e)
    if "not found" in msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)


_HANDLED = (DocumentRevisionError, PermissionError, ValueError)


# ── 엔드포인트 ────────────────────────────────────────────
@router.post(
    "/{kb_id}/documents/revision-check",
    response_model=RevisionCheckResponse,
    description=(
        "업로드 전 개정 여부 사전 점검 (document-revision §4.2 #1). 상태를 바꾸지 않는다. "
        "verdict=duplicate 면 같은 KB에 동일 파일이 있어 업로드할 수 없고, "
        "revision_candidate 면 suggested_document_id 의 개정본으로 올리기를 제안한다. "
        "응답 check_id 를 업로드 요청의 revision_check_id 로 넘기면 운영자 결정이 기록된다."
    ),
)
async def check_revision(
    kb_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    use_case: RevisionCheckUseCase = Depends(get_revision_check_use_case),
):
    request_id = str(uuid.uuid4())
    file_bytes = await file.read()
    filename = file.filename or "unknown.pdf"
    try:
        result = await use_case.execute(
            kb_id, current_user, file_bytes, filename, request_id
        )
    except _HANDLED as e:
        _raise_http(e)
    return RevisionCheckResponse.from_result(result)


@router.get(
    "/{kb_id}/documents/{document_id}/versions",
    response_model=DocumentVersionsResponse,
    description="문서 계보의 전체 버전 (최신순). KB 읽기 권한 (document-revision §4.2 #4).",
)
async def list_versions(
    kb_id: str,
    document_id: str,
    current_user: User = Depends(get_current_user),
    use_case: RevisionManagementUseCase = Depends(get_revision_management_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        versions = await use_case.versions(kb_id, document_id, current_user, request_id)
    except _HANDLED as e:
        _raise_http(e)
    items = [DocumentVersionResponse.from_version(v) for v in versions]
    return DocumentVersionsResponse(
        lineage_id=items[0].lineage_id if items else document_id, versions=items
    )


@router.post(
    "/{kb_id}/documents/{document_id}/revision-rollback",
    response_model=RollbackResponse,
    description=(
        "최신 버전의 개정을 취소한다. 이전 버전을 먼저 검색에 복귀시킨 뒤 현재 버전을 "
        "계보에서 분리(detach)하거나 삭제(delete)한다 (document-revision §4.2 #5)."
    ),
)
async def rollback_revision(
    kb_id: str,
    document_id: str,
    body: RollbackRequest,
    current_user: User = Depends(get_current_user),
    use_case: RevisionManagementUseCase = Depends(get_revision_management_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        result = await use_case.rollback(
            kb_id, document_id, body.mode, current_user, request_id
        )
    except _HANDLED as e:
        _raise_http(e)
    return RollbackResponse(
        restored_document_id=result.restored_document_id,
        detached_document_id=result.detached_document_id,
        deleted_document_id=result.deleted_document_id,
        sync_state=result.sync_state,
    )


@router.post(
    "/{kb_id}/documents/{document_id}/revision-link",
    response_model=LinkResponse,
    description=(
        "이미 올라간 두 문서를 개정 관계로 연결한다. document_id 가 신버전, "
        "supersedes_document_id 가 대체되는 구버전 (document-revision §4.2 #6)."
    ),
)
async def link_revision(
    kb_id: str,
    document_id: str,
    body: LinkRequest,
    current_user: User = Depends(get_current_user),
    use_case: RevisionManagementUseCase = Depends(get_revision_management_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        version, sync = await use_case.link(
            kb_id, document_id, body.supersedes_document_id, current_user, request_id
        )
    except _HANDLED as e:
        _raise_http(e)
    return LinkResponse(
        document=DocumentVersionResponse.from_version(version), sync_state=sync.value
    )


@router.patch(
    "/{kb_id}/documents/{document_id}/revision-meta",
    response_model=DocumentVersionResponse,
    description="버전 라벨·시행일 수정. 검색에는 영향 없음 (document-revision §4.2 #7).",
)
async def update_revision_meta(
    kb_id: str,
    document_id: str,
    body: RevisionMetaRequest,
    current_user: User = Depends(get_current_user),
    use_case: RevisionManagementUseCase = Depends(get_revision_management_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        version = await use_case.update_meta(
            kb_id, document_id, body.version_label or None, body.effective_date,
            current_user, request_id,
        )
    except _HANDLED as e:
        _raise_http(e)
    return DocumentVersionResponse.from_version(version)


@router.post(
    "/{kb_id}/documents/{document_id}/revision-sync",
    response_model=RevisionSyncResponse,
    description=(
        "MySQL 개정 상태를 기준으로 청크 검색 제외 표식을 다시 반영한다(멱등). "
        "sync_state=pending 문서의 재시도용 (document-revision §4.2 #8)."
    ),
)
async def retry_revision_sync(
    kb_id: str,
    document_id: str,
    current_user: User = Depends(get_current_user),
    use_case: RevisionManagementUseCase = Depends(get_revision_management_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        version = await use_case.resync(kb_id, document_id, current_user, request_id)
    except _HANDLED as e:
        _raise_http(e)
    return RevisionSyncResponse(
        document_id=version.document_id,
        revision_status=version.revision_status.value,
        sync_state=version.sync_state.value,
    )


@router.patch(
    "/{kb_id}/revision-mode",
    response_model=RevisionModeResponse,
    description=(
        "KB 개정 판정 모드. 현재는 suggest 만 저장되고 auto 는 422 "
        "(document-revision §4.2 #10, 판정 로그 실측 후 후속 사이클)."
    ),
)
async def update_revision_mode(
    kb_id: str,
    body: RevisionModeRequest,
    current_user: User = Depends(get_current_user),
    use_case: KnowledgeBaseUseCase = Depends(get_knowledge_base_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        kb = await use_case.update_revision_mode(
            kb_id, current_user, body.revision_mode, request_id
        )
    except _HANDLED as e:
        _raise_http(e)
    return RevisionModeResponse(kb_id=kb.id, revision_mode=kb.revision_mode)
