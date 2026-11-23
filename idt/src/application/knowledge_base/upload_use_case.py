"""KnowledgeBaseUploadUseCase — 지식베이스 지정 업로드 (Design §6.3).

물리 컬렉션은 KB 레코드에서 자동 결정하고, kb_id/kb_name을 extra_metadata로
UnifiedUploadUseCase에 위임해 Qdrant payload + ES 문서 양쪽에 주입한다.
"""
import hashlib

from src.application.document_revision.schemas import (
    KbUploadOutcome,
    RevisionApplyResult,
    RevisionUploadOptions,
)
from src.application.document_revision.supersede_service import SupersedeService
from src.application.knowledge_base.chunking_resolver import (
    ChunkingSettingsResolver,
)
from src.application.section_summary.launcher import SectionSummaryLauncher
from src.application.section_summary.schemas import (
    SectionSummaryLaunchInfo,
    SectionSummaryLaunchInput,
)
from src.application.unified_upload.schemas import (
    UnifiedUploadRequest,
    UnifiedUploadResult,
)
from src.application.unified_upload.use_case import UnifiedUploadUseCase
from src.domain.auth.entities import User
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.document_revision.errors import (
    DuplicateDocumentError,
    RevisionTargetInvalidError,
)
from src.domain.document_revision.interfaces import (
    DocumentRevisionRepositoryPort,
    RevisionCheckLogRepositoryPort,
)
from src.domain.document_revision.policy import RevisionPolicy
from src.domain.document_revision.value_objects import (
    CheckDecision,
    DocumentVersion,
)
from src.domain.extension_hooks import DocumentIngestedEvent, ExtensionHooks
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.interfaces import (
    KnowledgeBaseRepositoryInterface,
)
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.parser.supported_formats import FORMAT_EXCEL, resolve_format

_DEFAULT_CHILD_SIZE = 500
_DEFAULT_CHILD_OVERLAP = 50


class KnowledgeBaseUploadUseCase:
    def __init__(
        self,
        kb_repo: KnowledgeBaseRepositoryInterface,
        policy: KnowledgeBasePolicy,
        dept_repo: DepartmentRepositoryInterface,
        unified_upload: UnifiedUploadUseCase,
        logger: LoggerInterface,
        chunking_resolver: ChunkingSettingsResolver | None = None,
        summary_launcher: SectionSummaryLauncher | None = None,
        extension_hooks: ExtensionHooks | None = None,
        revision_repo: DocumentRevisionRepositoryPort | None = None,
        supersede_service: SupersedeService | None = None,
        check_log_repo: RevisionCheckLogRepositoryPort | None = None,
    ) -> None:
        # graph-rag-foundation §2.2: 업로드 후 확장 훅(그래프 추출 등). 미등록 = 무동작.
        self._extension_hooks = extension_hooks
        # document-revision Design §2.1: 미주입이면 해시 중복 검사·개정 없이 기존 동작
        self._revision_repo = revision_repo
        self._supersede = supersede_service
        self._check_log = check_log_repo
        self._kb_repo = kb_repo
        self._policy = policy
        self._dept_repo = dept_repo
        self._unified_upload = unified_upload
        self._logger = logger
        self._chunking_resolver = chunking_resolver
        self._summary_launcher = summary_launcher

    async def execute(
        self,
        kb_id: str,
        user: User,
        file_bytes: bytes,
        filename: str,
        request_id: str,
        child_chunk_size: int = 500,
        child_chunk_overlap: int = 50,
    ) -> tuple[
        UnifiedUploadResult, KnowledgeBase, SectionSummaryLaunchInfo | None
    ]:
        """기존 3-tuple 계약 (quick create 등). 개정 입력 없이 업로드한다."""
        outcome = await self.execute_with_revision(
            kb_id, user, file_bytes, filename, request_id,
            child_chunk_size=child_chunk_size,
            child_chunk_overlap=child_chunk_overlap,
        )
        return outcome.result, outcome.kb, outcome.summary_launch

    async def execute_with_revision(
        self,
        kb_id: str,
        user: User,
        file_bytes: bytes,
        filename: str,
        request_id: str,
        child_chunk_size: int = 500,
        child_chunk_overlap: int = 50,
        revision: RevisionUploadOptions | None = None,
    ) -> KbUploadOutcome:
        """Design Ref: document-revision §2.2 확정 업로드.

        권한 → 해시 중복(적재 전 차단) → 대체 대상 검증(적재 전) → 적재 →
        completed 일 때만 구버전 전환. partial/failed 면 신규 문서를 계보에서 분리한다.
        """
        revision = revision or RevisionUploadOptions()
        kb = await self._kb_repo.find_by_id(kb_id, request_id)
        if kb is None:
            raise ValueError(f"Knowledge base '{kb_id}' not found")

        dept_ids = await self._get_dept_ids(user, request_id)
        if not self._policy.can_write(user, kb, dept_ids):
            raise PermissionError(
                f"No write access to knowledge base '{kb_id}'"
            )

        file_hash = hashlib.sha256(file_bytes).hexdigest()
        await self._reject_duplicate(kb.id, file_hash, request_id)
        target, lineage_id, version_no = await self._resolve_target(
            kb.id, revision.supersedes_document_id, request_id
        )

        is_excel = resolve_format(filename) == FORMAT_EXCEL
        chunking_config = await self._resolve_chunking(
            kb, child_chunk_size, child_chunk_overlap, request_id,
            is_excel=is_excel,
        )
        unified_req = UnifiedUploadRequest(
            file_bytes=file_bytes,
            filename=filename,
            user_id=str(user.id),
            collection_name=kb.collection_name,
            child_chunk_size=child_chunk_size,
            child_chunk_overlap=child_chunk_overlap,
            extra_metadata={"kb_id": kb.id, "kb_name": kb.name},
            chunking_config=chunking_config,
            file_hash=file_hash,
            lineage_id=lineage_id,
            version_no=version_no,
            version_label=revision.version_label,
            effective_date=revision.effective_date,
        )
        self._logger.info(
            "KnowledgeBase upload delegating",
            request_id=request_id,
            kb_id=kb.id,
            collection_name=kb.collection_name,
            filename=filename,
        )
        result = await self._unified_upload.execute(unified_req, request_id)
        revision_result = await self._apply_revision(
            kb, target, lineage_id, version_no, result, user, request_id
        )
        await self._record_decision(revision, revision_result, result, user, request_id)
        summary_launch = await self._launch_summary(
            kb, result, request_id, is_excel=is_excel
        )
        await self._notify_post_ingest(kb, result, user, filename, request_id)
        return KbUploadOutcome(
            result=result, kb=kb, summary_launch=summary_launch,
            revision=revision_result,
        )

    # ── document-revision ─────────────────────────────────
    async def _reject_duplicate(
        self, kb_id: str, file_hash: str, request_id: str
    ) -> None:
        """Plan SC-2: 같은 KB 에 바이트가 같은 파일이 있으면 적재 전 차단."""
        if self._revision_repo is None:
            return
        matches = await self._revision_repo.find_by_hash(kb_id, file_hash, request_id)
        if not matches:
            return
        existing = next((m for m in matches if m.is_active), matches[0])
        self._logger.info(
            "Duplicate document rejected",
            request_id=request_id,
            kb_id=kb_id,
            existing_document_id=existing.document_id,
        )
        raise DuplicateDocumentError(existing)

    async def _resolve_target(
        self, kb_id: str, supersedes_document_id: str | None, request_id: str
    ) -> tuple[DocumentVersion | None, str | None, int]:
        """대체 대상 검증 → (대상, 계보 ID, 신규 버전 번호). 대상 없음 = (None, None, 1)."""
        if not supersedes_document_id:
            return None, None, 1
        if self._revision_repo is None or self._supersede is None:
            raise RevisionTargetInvalidError(
                "not_supported", "개정 업로드가 구성되지 않았습니다"
            )
        target = await self._revision_repo.find_version(
            supersedes_document_id, request_id
        )
        lineage = (
            await self._revision_repo.find_lineage_versions(
                target.effective_lineage_id, request_id
            )
            if target
            else []
        )
        RevisionPolicy.validate_supersede_target(target, kb_id, lineage)
        return target, target.effective_lineage_id, RevisionPolicy.next_version_no(
            lineage
        )

    async def _apply_revision(
        self,
        kb: KnowledgeBase,
        target: DocumentVersion | None,
        lineage_id: str | None,
        version_no: int,
        result: UnifiedUploadResult,
        user: User,
        request_id: str,
    ) -> RevisionApplyResult:
        if target is None:
            return RevisionApplyResult(
                applied=False, lineage_id=None, version_no=1,
                superseded_document_id=None, sync_state=None,
            )
        if result.status != "completed":
            # 신버전이 온전히 적재되지 않았으면 구버전을 유지하고 신규 문서를 계보에서 뗀다
            await self._revision_repo.assign_lineage(
                result.document_id, lineage_id=None, version_no=1,
                request_id=request_id,
            )
            self._logger.warning(
                "Revision not applied: ingest incomplete",
                request_id=request_id,
                document_id=result.document_id,
                status=result.status,
            )
            return RevisionApplyResult(
                applied=False, lineage_id=None, version_no=1,
                superseded_document_id=None, sync_state=None,
                reason="ingest_incomplete",
            )
        sync_state = await self._supersede.supersede(
            target, result.document_id, kb.collection_name,
            revised_by=str(user.id), request_id=request_id,
        )
        return RevisionApplyResult(
            applied=True, lineage_id=lineage_id, version_no=version_no,
            superseded_document_id=target.document_id,
            sync_state=sync_state.value,
        )

    async def _record_decision(
        self,
        revision: RevisionUploadOptions,
        applied: RevisionApplyResult,
        result: UnifiedUploadResult,
        user: User,
        request_id: str,
    ) -> None:
        """판정 로그에 운영자 결정 기록 — 실패해도 업로드는 성공으로 둔다."""
        if not revision.revision_check_id or self._check_log is None:
            return
        try:
            await self._check_log.record_decision(
                revision.revision_check_id,
                decision=(
                    CheckDecision.REVISION if applied.applied else CheckDecision.NEW
                ),
                target_document_id=applied.superseded_document_id,
                decided_document_id=result.document_id,
                decided_by=str(user.id),
                request_id=request_id,
            )
        except Exception as e:
            self._logger.warning(
                "Revision decision log failed (upload unaffected)",
                request_id=request_id,
                check_id=revision.revision_check_id,
                exception=e,
            )

    async def _notify_post_ingest(
        self,
        kb: KnowledgeBase,
        result: UnifiedUploadResult,
        user: User,
        filename: str,
        request_id: str,
    ) -> None:
        """확장 훅 통지 — 실패는 로그만 남기고 업로드 결과를 바꾸지 않는다 (§6.2)."""
        hook = self._extension_hooks.post_ingest if self._extension_hooks else None
        if hook is None:
            return
        event = DocumentIngestedEvent(
            document_id=result.document_id,
            kb_id=kb.id,
            collection_name=kb.collection_name,
            filename=filename,
            user_id=str(user.id),
            chunk_count=result.chunk_count,
            status=result.status,
        )
        try:
            await hook.on_document_ingested(event, request_id)
        except Exception as e:
            self._logger.error(
                "Post-ingest hook failed (upload unaffected)",
                request_id=request_id,
                document_id=result.document_id,
                exception=e,
            )

    async def _launch_summary(
        self,
        kb: KnowledgeBase,
        result: UnifiedUploadResult,
        request_id: str,
        *,
        is_excel: bool = False,
    ) -> SectionSummaryLaunchInfo | None:
        """섹션 요약 잡 킥오프 (card-section-summary D14).

        요약 비활성/업로드 실패면 None. launcher 내부 실패도 None —
        업로드 결과에 영향을 주지 않는다 (FR-09).
        엑셀은 조항 청킹 전제 기능이므로 스킵한다 (kb-excel-upload D8).
        """
        if is_excel:
            self._logger.info(
                "Section summary skipped for excel upload",
                request_id=request_id,
                kb_id=kb.id,
            )
            return None
        if (
            self._summary_launcher is None
            or self._chunking_resolver is None
            or result.status == "failed"
        ):
            return None
        spec = await self._chunking_resolver.resolve_summary_spec(
            kb, request_id
        )
        if spec is None:
            return None
        return await self._summary_launcher.launch(
            SectionSummaryLaunchInput(
                document_id=result.document_id,
                kb_id=kb.id,
                collection_name=kb.collection_name,
                profile_id=spec.profile_id,
                llm_model_id=spec.llm_model_id,
                embedding_model_name=result.qdrant.embedding_model,
            ),
            request_id,
        )

    async def _resolve_chunking(
        self,
        kb: KnowledgeBase,
        child_chunk_size: int,
        child_chunk_overlap: int,
        request_id: str,
        *,
        is_excel: bool = False,
    ):
        """KB 청킹 설정 해석. clause/custom 활성 시 Query 파라미터 무시 (Design D6).

        엑셀은 텍스트 전제 청킹 설정(clause/custom)을 우회하고 기본
        parent_child 경로를 쓴다 (kb-excel-upload D7).
        """
        if is_excel:
            if kb.use_clause_chunking or kb.use_custom_chunking:
                self._logger.warning(
                    "Excel bypasses KB chunking settings",
                    request_id=request_id,
                    kb_id=kb.id,
                )
            return None
        if self._chunking_resolver is None:
            return None
        config = await self._chunking_resolver.resolve(kb, request_id)
        if config is not None and (
            child_chunk_size != _DEFAULT_CHILD_SIZE
            or child_chunk_overlap != _DEFAULT_CHILD_OVERLAP
        ):
            self._logger.warning(
                "Query chunk params ignored (KB chunking settings active)",
                request_id=request_id,
                kb_id=kb.id,
            )
        return config

    async def _get_dept_ids(self, user: User, request_id: str) -> list[str]:
        if user.id is None:
            return []
        depts = await self._dept_repo.find_departments_by_user(
            user.id, request_id
        )
        return [d.department_id for d in depts]
