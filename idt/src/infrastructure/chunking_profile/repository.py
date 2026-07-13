"""ChunkingProfileRepository — MySQL 영속화 (clause-aware-chunking Design §5.3)."""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.chunking_profile.entities import BoundaryRule, ChunkingProfile
from src.domain.chunking_profile.interfaces import (
    ChunkingProfileRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.persistence.models.chunking_profile import (
    ChunkingProfileModel,
)


class ChunkingProfileRepository(ChunkingProfileRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(
        self, profile: ChunkingProfile, request_id: str
    ) -> ChunkingProfile:
        self._logger.info(
            "ChunkingProfile save",
            request_id=request_id,
            profile_id=profile.id,
        )
        model = ChunkingProfileModel(
            id=profile.id,
            name=profile.name,
            description=profile.description,
            boundary_rules=self._rules_to_json(profile.boundary_rules),
            parent_chunk_size=profile.parent_chunk_size,
            chunk_size=profile.chunk_size,
            chunk_overlap=profile.chunk_overlap,
            is_default=1 if profile.is_default else 0,
            summary_llm_model_id=profile.summary_llm_model_id,
            status=profile.status,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_domain(model)

    async def find_by_id(
        self, profile_id: str, request_id: str
    ) -> ChunkingProfile | None:
        stmt = select(ChunkingProfileModel).where(
            ChunkingProfileModel.id == profile_id
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_all_active(
        self, request_id: str
    ) -> list[ChunkingProfile]:
        stmt = select(ChunkingProfileModel).where(
            ChunkingProfileModel.status == "active"
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_default(
        self, request_id: str
    ) -> ChunkingProfile | None:
        stmt = select(ChunkingProfileModel).where(
            ChunkingProfileModel.is_default == 1,
            ChunkingProfileModel.status == "active",
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model else None

    async def exists_active_name(
        self, name: str, exclude_id: str | None, request_id: str
    ) -> bool:
        stmt = select(ChunkingProfileModel.id).where(
            ChunkingProfileModel.name == name,
            ChunkingProfileModel.status == "active",
        )
        if exclude_id is not None:
            stmt = stmt.where(ChunkingProfileModel.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def update(
        self, profile: ChunkingProfile, request_id: str
    ) -> ChunkingProfile:
        stmt = (
            update(ChunkingProfileModel)
            .where(ChunkingProfileModel.id == profile.id)
            .values(
                name=profile.name,
                description=profile.description,
                boundary_rules=self._rules_to_json(profile.boundary_rules),
                parent_chunk_size=profile.parent_chunk_size,
                chunk_size=profile.chunk_size,
                chunk_overlap=profile.chunk_overlap,
                is_default=1 if profile.is_default else 0,
                summary_llm_model_id=profile.summary_llm_model_id,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return await self.find_by_id(profile.id, request_id)

    async def clear_default(self, request_id: str) -> None:
        stmt = (
            update(ChunkingProfileModel)
            .where(ChunkingProfileModel.is_default == 1)
            .values(is_default=0)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def soft_delete(self, profile_id: str, request_id: str) -> None:
        stmt = (
            update(ChunkingProfileModel)
            .where(ChunkingProfileModel.id == profile_id)
            .values(status="deleted")
        )
        await self._session.execute(stmt)
        await self._session.flush()

    @staticmethod
    def _rules_to_json(rules: list[BoundaryRule]) -> list[dict]:
        return [
            {"pattern": r.pattern, "priority": r.priority, "level": r.level}
            for r in rules
        ]

    def _to_domain(self, model: ChunkingProfileModel) -> ChunkingProfile:
        rules = [
            BoundaryRule(
                pattern=r["pattern"],
                priority=r["priority"],
                level=r["level"],
            )
            for r in (model.boundary_rules or [])
        ]
        return ChunkingProfile(
            id=model.id,
            name=model.name,
            description=model.description,
            boundary_rules=rules,
            parent_chunk_size=model.parent_chunk_size,
            chunk_size=model.chunk_size,
            chunk_overlap=model.chunk_overlap,
            is_default=bool(model.is_default),
            summary_llm_model_id=model.summary_llm_model_id,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
