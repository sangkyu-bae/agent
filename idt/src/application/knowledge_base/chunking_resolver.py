"""ChunkingSettingsResolver — KB의 청킹 설정을 업로드용 config로 해석 (Design §7.2, D11).

use_clause_chunking=False면 None(기존 경로). True면 프로파일 로드 → KB 오버라이드 병합.
참조 프로파일이 없거나 soft-deleted면 default 폴백, default도 없으면 None(legacy)으로
폴백해 업로드가 항상 성공하도록 한다 (FR-07).
"""
from src.application.unified_upload.schemas import UploadChunkingConfig
from src.domain.chunking_profile.entities import ChunkingProfile
from src.domain.chunking_profile.interfaces import (
    ChunkingProfileRepositoryInterface,
)
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.section_summary.entities import SectionSummarySpec


class ChunkingSettingsResolver:
    def __init__(
        self,
        profile_repo: ChunkingProfileRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._profile_repo = profile_repo
        self._logger = logger

    async def resolve(
        self, kb: KnowledgeBase, request_id: str
    ) -> UploadChunkingConfig | None:
        if not kb.use_clause_chunking:
            return None

        profile = await self._load_profile(kb, request_id)
        if profile is None:
            self._logger.warning(
                "No usable chunking profile, falling back to legacy path",
                request_id=request_id,
                kb_id=kb.id,
            )
            return None

        chunk_size = kb.chunk_size or profile.chunk_size
        chunk_overlap = (
            kb.chunk_overlap
            if kb.chunk_overlap is not None
            else profile.chunk_overlap
        )
        params = {
            "parent_patterns": profile.parent_patterns(),
            "child_patterns": profile.child_patterns(),
            "parent_chunk_size": profile.parent_chunk_size,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        display = {
            "strategy": "clause_aware",
            "profile_id": profile.id,
            "profile_name": profile.name,
            "parent_chunk_size": profile.parent_chunk_size,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }
        return UploadChunkingConfig(
            strategy="clause_aware", params=params, display=display
        )

    async def resolve_summary_spec(
        self, kb: KnowledgeBase, request_id: str
    ) -> SectionSummarySpec | None:
        """섹션 요약 실행 사양 해석 (card-section-summary D14).

        clause chunking 활성 + 프로파일에 summary_llm_model_id가 있을 때만
        스펙을 반환한다 (None = 요약 비활성).
        """
        if not kb.use_clause_chunking:
            return None
        profile = await self._load_profile(kb, request_id)
        if profile is None or not profile.summary_llm_model_id:
            return None
        return SectionSummarySpec(
            llm_model_id=profile.summary_llm_model_id,
            profile_id=profile.id,
        )

    async def _load_profile(
        self, kb: KnowledgeBase, request_id: str
    ) -> ChunkingProfile | None:
        if kb.chunking_profile_id:
            profile = await self._profile_repo.find_by_id(
                kb.chunking_profile_id, request_id
            )
            if profile is not None and profile.status == "active":
                return profile
            self._logger.warning(
                "Chunking profile missing/deleted, falling back to default",
                request_id=request_id,
                kb_id=kb.id,
                chunking_profile_id=kb.chunking_profile_id,
            )
        return await self._profile_repo.find_default(request_id)
