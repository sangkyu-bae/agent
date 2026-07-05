"""SkillRepository: MySQLBaseRepository 기반 skill_definition 저장소."""
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.skill_builder.interfaces import SkillRepositoryInterface
from src.domain.skill_builder.schemas import (
    SkillDefinition,
    SkillScriptType,
    SkillVisibility,
)
from src.infrastructure.persistence.models.skill_builder.models import (
    SkillDefinitionModel,
)
from src.infrastructure.persistence.mysql_base_repository import MySQLBaseRepository


def _to_model(entity: SkillDefinition) -> SkillDefinitionModel:
    return SkillDefinitionModel(
        id=entity.id,
        user_id=entity.user_id,
        name=entity.name,
        description=entity.description,
        trigger=entity.trigger,
        instruction=entity.instruction,
        script_type=entity.script_type.value,
        script_content=entity.script_content,
        status=entity.status,
        visibility=entity.visibility.value,
        department_id=entity.department_id,
        forked_from=entity.forked_from,
        forked_at=entity.forked_at,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _to_entity(model: SkillDefinitionModel) -> SkillDefinition:
    return SkillDefinition(
        id=model.id,
        user_id=model.user_id,
        name=model.name,
        description=model.description,
        instruction=model.instruction,
        trigger=model.trigger,
        script_type=SkillScriptType(model.script_type),
        script_content=model.script_content,
        status=model.status,
        visibility=SkillVisibility(model.visibility),
        department_id=model.department_id,
        forked_from=model.forked_from,
        forked_at=model.forked_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SkillRepository(
    MySQLBaseRepository[SkillDefinitionModel],
    SkillRepositoryInterface,
):
    def __init__(self, session: AsyncSession, logger: LoggerInterface):
        super().__init__(session, SkillDefinitionModel, logger)

    # ── 내부 위임 (테스트 패치 포인트) ──────────────────────────────

    async def _base_save(
        self, model: SkillDefinitionModel, request_id: str
    ) -> SkillDefinitionModel:
        return await MySQLBaseRepository.save(self, model, request_id)

    async def _base_find_by_id(
        self, skill_id: str, request_id: str
    ) -> SkillDefinitionModel | None:
        return await MySQLBaseRepository.find_by_id(self, skill_id, request_id)

    # ── SkillRepositoryInterface 구현 ──────────────────────────────

    async def save(self, skill: SkillDefinition, request_id: str) -> SkillDefinition:
        saved = await self._base_save(_to_model(skill), request_id)
        return _to_entity(saved)

    async def find_by_id(
        self, skill_id: str, request_id: str
    ) -> SkillDefinition | None:
        model = await self._base_find_by_id(skill_id, request_id)
        return _to_entity(model) if model else None

    async def update(self, skill: SkillDefinition, request_id: str) -> SkillDefinition:
        merged = await self._session.merge(_to_model(skill))
        await self._session.flush()
        return _to_entity(merged)

    async def list_by_user(
        self, user_id: str, request_id: str
    ) -> list[SkillDefinition]:
        stmt = select(SkillDefinitionModel).where(
            SkillDefinitionModel.user_id == user_id,
            SkillDefinitionModel.status != "deleted",
        ).order_by(SkillDefinitionModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [_to_entity(m) for m in result.scalars().all()]

    async def list_accessible(
        self,
        viewer_user_id: str,
        viewer_department_ids: list[str],
        scope: str,
        search: str | None,
        page: int,
        size: int,
        request_id: str,
    ) -> tuple[list[SkillDefinition], int]:
        self._logger.info(
            "Skill list_accessible", request_id=request_id, scope=scope
        )
        try:
            base = select(SkillDefinitionModel).where(
                SkillDefinitionModel.status != "deleted"
            )
            base = self._apply_scope(base, scope, viewer_user_id, viewer_department_ids)
            if search:
                like = f"%{search}%"
                base = base.where(
                    or_(
                        SkillDefinitionModel.name.ilike(like),
                        SkillDefinitionModel.description.ilike(like),
                    )
                )

            count_stmt = select(func.count()).select_from(base.subquery())
            total = (await self._session.execute(count_stmt)).scalar_one()

            offset = (page - 1) * size
            data_stmt = (
                base.order_by(SkillDefinitionModel.created_at.desc())
                .offset(offset)
                .limit(size)
            )
            result = await self._session.execute(data_stmt)
            skills = [_to_entity(m) for m in result.scalars().all()]
            return skills, total
        except Exception as e:
            self._logger.error(
                "Skill list_accessible failed", exception=e, request_id=request_id
            )
            raise

    @staticmethod
    def _apply_scope(stmt, scope, viewer_user_id, viewer_department_ids):
        """scope별 가시성 필터를 select 문에 적용한다."""
        dept_ids = viewer_department_ids if viewer_department_ids else [""]
        if scope == "mine":
            return stmt.where(SkillDefinitionModel.user_id == viewer_user_id)
        if scope == "department":
            return stmt.where(
                SkillDefinitionModel.visibility == "department",
                SkillDefinitionModel.department_id.in_(dept_ids),
            )
        if scope == "public":
            return stmt.where(SkillDefinitionModel.visibility == "public")
        return stmt.where(
            or_(
                SkillDefinitionModel.user_id == viewer_user_id,
                SkillDefinitionModel.visibility == "public",
                and_(
                    SkillDefinitionModel.visibility == "department",
                    SkillDefinitionModel.department_id.in_(dept_ids),
                ),
            )
        )

    async def soft_delete(self, skill_id: str, request_id: str) -> None:
        model = await self._base_find_by_id(skill_id, request_id)
        if model is None:
            return
        model.status = "deleted"
        await self._base_save(model, request_id)
