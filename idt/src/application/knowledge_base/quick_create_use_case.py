"""QuickCreateKnowledgeBaseUseCase — KB 생성 + 전용 컬렉션 + 파일 순차 업로드.

agent-kb-quick-setup Design §4.2 (/quick) / §1.2.
- KB 생성·컬렉션 생성 실패는 **전파**한다 (파일 업로드 시작 전).
- 파일 단위 실패만 status=failed 로 응답에 남긴다 — 광역 흡수 지점은 `_upload_one`
  1곳뿐이며 AST 계약 테스트가 이를 고정한다 (degradation-vs-failure-boundary).
- 청킹은 KB 기본(프로파일 is_default)을 그대로 따른다 — 오버라이드를 넘기지 않는다
  (FR-05).
"""
from dataclasses import dataclass

from src.application.knowledge_base.upload_use_case import (
    KnowledgeBaseUploadUseCase,
)
from src.application.knowledge_base.use_case import KnowledgeBaseUseCase
from src.domain.auth.entities import User
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.quick_setup_policy import KbQuickSetupPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface

DOC_STATUS_UPLOADED = "uploaded"
DOC_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class QuickFile:
    filename: str
    content: bytes


@dataclass(frozen=True)
class QuickDocumentResult:
    filename: str
    status: str  # uploaded | failed
    document_id: str | None
    chunk_count: int
    error: str | None


@dataclass(frozen=True)
class QuickCreateResult:
    kb: KnowledgeBase
    documents: tuple[QuickDocumentResult, ...]
    uploaded_count: int
    failed_count: int


class QuickCreateKnowledgeBaseUseCase:
    def __init__(
        self,
        kb_use_case: KnowledgeBaseUseCase,
        upload_use_case: KnowledgeBaseUploadUseCase,
        logger: LoggerInterface,
    ) -> None:
        self._kb = kb_use_case
        self._upload = upload_use_case
        self._logger = logger

    async def execute(
        self,
        *,
        user: User,
        name: str,
        scope: CollectionScope,
        department_id: str | None,
        files: list[QuickFile],
        request_id: str,
    ) -> QuickCreateResult:
        KbQuickSetupPolicy.validate_files([f.filename for f in files])
        kb = await self._create_with_unique_name(
            user, name, scope, department_id, request_id
        )
        documents = [await self._upload_one(kb, user, f, request_id) for f in files]
        uploaded = sum(1 for d in documents if d.status == DOC_STATUS_UPLOADED)
        self._logger.info(
            "Quick KB setup finished",
            request_id=request_id,
            kb_id=kb.id,
            uploaded=uploaded,
            failed=len(documents) - uploaded,
        )
        return QuickCreateResult(
            kb=kb,
            documents=tuple(documents),
            uploaded_count=uploaded,
            failed_count=len(documents) - uploaded,
        )

    async def _create_with_unique_name(
        self,
        user: User,
        base_name: str,
        scope: CollectionScope,
        department_id: str | None,
        request_id: str,
    ) -> KnowledgeBase:
        """이름 중복이면 " (2)" ~ " (20)" 접미로 재시도. 그 외 오류는 그대로 전파."""
        attempt = 0
        while True:
            candidate = KbQuickSetupPolicy.next_name(base_name, attempt)
            try:
                return await self._kb.create(
                    user=user,
                    name=candidate,
                    collection_name=None,
                    scope=scope,
                    department_id=department_id,
                    description=None,
                    request_id=request_id,
                )
            except ValueError as e:
                if "already exists" not in str(e) or "Knowledge base" not in str(e):
                    raise
                attempt += 1

    async def _upload_one(
        self, kb: KnowledgeBase, user: User, file: QuickFile, request_id: str
    ) -> QuickDocumentResult:
        """유일한 광역 흡수 지점 — KB 는 이미 존재하므로 파일 실패는 degraded."""
        try:
            result, _, _ = await self._upload.execute(
                kb.id, user, file.content, file.filename, request_id
            )
        except Exception as e:
            self._logger.warning(
                "Quick KB upload failed for file",
                request_id=request_id,
                kb_id=kb.id,
                filename=file.filename,
                exception=e,
            )
            return QuickDocumentResult(
                filename=file.filename,
                status=DOC_STATUS_FAILED,
                document_id=None,
                chunk_count=0,
                error=str(e),
            )
        if result.status == "failed":
            return QuickDocumentResult(
                filename=file.filename,
                status=DOC_STATUS_FAILED,
                document_id=result.document_id,
                chunk_count=result.chunk_count,
                error=result.qdrant.error or result.es.error or "저장 실패",
            )
        return QuickDocumentResult(
            filename=file.filename,
            status=DOC_STATUS_UPLOADED,
            document_id=result.document_id,
            chunk_count=result.chunk_count,
            error=None,
        )
