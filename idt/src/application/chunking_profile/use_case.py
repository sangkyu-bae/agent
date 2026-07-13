"""ChunkingProfileUseCase — 관리자 CRUD + 사용자 목록 (clause-aware-chunking Design §7.1).

is_default 유일성은 단일 세션 내 clear_default → 지정 순서로 보장한다 (Design D3).
"""
import uuid

from src.domain.chunking_profile.entities import BoundaryRule, ChunkingProfile
from src.domain.chunking_profile.interfaces import (
    ChunkingProfileRepositoryInterface,
)
from src.domain.chunking_profile.policy import ChunkingProfilePolicy
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ChunkingProfileUseCase:
    def __init__(
        self,
        profile_repo: ChunkingProfileRepositoryInterface,
        policy: ChunkingProfilePolicy,
        logger: LoggerInterface,
        llm_model_repo: LlmModelRepositoryInterface | None = None,
    ) -> None:
        self._repo = profile_repo
        self._policy = policy
        self._logger = logger
        self._llm_model_repo = llm_model_repo

    async def _validate_summary_model(
        self, summary_llm_model_id: str | None, request_id: str
    ) -> None:
        """섹션 요약 모델 존재+활성 검증 (card-section-summary D16)."""
        if summary_llm_model_id is None or self._llm_model_repo is None:
            return
        model = await self._llm_model_repo.find_by_id(
            summary_llm_model_id, request_id
        )
        if model is None or not model.is_active:
            raise ValueError(
                f"summary_llm_model_id '{summary_llm_model_id}' is not an "
                "active LLM model"
            )

    async def create(
        self,
        name: str,
        boundary_rules: list[BoundaryRule],
        parent_chunk_size: int,
        chunk_size: int,
        chunk_overlap: int,
        description: str | None,
        is_default: bool,
        request_id: str,
        summary_llm_model_id: str | None = None,
    ) -> ChunkingProfile:
        clean_name = self._policy.validate_name(name)
        self._policy.validate_rules(boundary_rules)
        self._policy.validate_sizes(parent_chunk_size, chunk_size, chunk_overlap)
        await self._validate_summary_model(summary_llm_model_id, request_id)
        if await self._repo.exists_active_name(clean_name, None, request_id):
            raise ValueError(f"Chunking profile '{clean_name}' already exists")
        if is_default:
            await self._repo.clear_default(request_id)
        profile = ChunkingProfile(
            id=str(uuid.uuid4()),
            name=clean_name,
            description=description,
            boundary_rules=boundary_rules,
            parent_chunk_size=parent_chunk_size,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            is_default=is_default,
            summary_llm_model_id=summary_llm_model_id,
        )
        saved = await self._repo.save(profile, request_id)
        self._logger.info(
            "ChunkingProfile created",
            request_id=request_id,
            profile_id=saved.id,
            is_default=is_default,
        )
        return saved

    async def list_active(self, request_id: str) -> list[ChunkingProfile]:
        return await self._repo.find_all_active(request_id)

    async def get(self, profile_id: str, request_id: str) -> ChunkingProfile:
        profile = await self._repo.find_by_id(profile_id, request_id)
        if profile is None or profile.status != "active":
            raise ValueError(f"Chunking profile '{profile_id}' not found")
        return profile

    async def update(
        self,
        profile_id: str,
        name: str,
        boundary_rules: list[BoundaryRule],
        parent_chunk_size: int,
        chunk_size: int,
        chunk_overlap: int,
        description: str | None,
        is_default: bool,
        request_id: str,
        summary_llm_model_id: str | None = None,
    ) -> ChunkingProfile:
        existing = await self.get(profile_id, request_id)
        clean_name = self._policy.validate_name(name)
        self._policy.validate_rules(boundary_rules)
        self._policy.validate_sizes(parent_chunk_size, chunk_size, chunk_overlap)
        await self._validate_summary_model(summary_llm_model_id, request_id)
        if await self._repo.exists_active_name(
            clean_name, profile_id, request_id
        ):
            raise ValueError(f"Chunking profile '{clean_name}' already exists")
        if is_default and not existing.is_default:
            await self._repo.clear_default(request_id)
        updated = ChunkingProfile(
            id=profile_id,
            name=clean_name,
            description=description,
            boundary_rules=boundary_rules,
            parent_chunk_size=parent_chunk_size,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            is_default=is_default,
            summary_llm_model_id=summary_llm_model_id,
        )
        return await self._repo.update(updated, request_id)

    async def set_default(
        self, profile_id: str, request_id: str
    ) -> ChunkingProfile:
        profile = await self.get(profile_id, request_id)
        await self._repo.clear_default(request_id)
        profile.is_default = True
        result = await self._repo.update(profile, request_id)
        self._logger.info(
            "ChunkingProfile default set",
            request_id=request_id,
            profile_id=profile_id,
        )
        return result

    async def delete(self, profile_id: str, request_id: str) -> None:
        profile = await self.get(profile_id, request_id)
        self._policy.can_delete(profile)
        await self._repo.soft_delete(profile_id, request_id)
        self._logger.info(
            "ChunkingProfile soft-deleted",
            request_id=request_id,
            profile_id=profile_id,
        )
