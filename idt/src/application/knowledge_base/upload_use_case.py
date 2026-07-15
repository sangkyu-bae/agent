"""KnowledgeBaseUploadUseCase — 지식베이스 지정 업로드 (Design §6.3).

물리 컬렉션은 KB 레코드에서 자동 결정하고, kb_id/kb_name을 extra_metadata로
UnifiedUploadUseCase에 위임해 Qdrant payload + ES 문서 양쪽에 주입한다.
"""
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
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.interfaces import (
    KnowledgeBaseRepositoryInterface,
)
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface

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
    ) -> None:
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
        kb = await self._kb_repo.find_by_id(kb_id, request_id)
        if kb is None:
            raise ValueError(f"Knowledge base '{kb_id}' not found")

        dept_ids = await self._get_dept_ids(user, request_id)
        if not self._policy.can_write(user, kb, dept_ids):
            raise PermissionError(
                f"No write access to knowledge base '{kb_id}'"
            )

        chunking_config = await self._resolve_chunking(
            kb, child_chunk_size, child_chunk_overlap, request_id
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
        )
        self._logger.info(
            "KnowledgeBase upload delegating",
            request_id=request_id,
            kb_id=kb.id,
            collection_name=kb.collection_name,
            filename=filename,
        )
        result = await self._unified_upload.execute(unified_req, request_id)
        summary_launch = await self._launch_summary(kb, result, request_id)
        return result, kb, summary_launch

    async def _launch_summary(
        self,
        kb: KnowledgeBase,
        result: UnifiedUploadResult,
        request_id: str,
    ) -> SectionSummaryLaunchInfo | None:
        """섹션 요약 잡 킥오프 (card-section-summary D14).

        요약 비활성/업로드 실패면 None. launcher 내부 실패도 None —
        업로드 결과에 영향을 주지 않는다 (FR-09).
        """
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
    ):
        """KB 청킹 설정 해석. clause/custom 활성 시 Query 파라미터 무시 (Design D6)."""
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
