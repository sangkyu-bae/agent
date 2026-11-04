"""ToolAccessRepository — 도구 허용 규칙 MySQL 저장소.

Design Ref: tool-access-control §3.3, §3.5
- find_grants_for: 세 테이블 UNION 1회 (실행당 조회 비용 최소화).
- replace_*: scope(활성 카탈로그) 안에서만 DELETE + INSERT. commit 은 요청 세션
  경계(get_session)가 맡는다 — 저장소는 flush 까지만.
"""
from collections.abc import Iterable, Sequence

from sqlalchemy import delete, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_access.interfaces import ToolAccessRepositoryInterface
from src.infrastructure.tool_access.models import (
    ToolAccessDefaultModel,
    ToolAccessDepartmentModel,
    ToolAccessUserModel,
)


def _in_scope(tool_ids: Iterable[str], scope: frozenset[str]) -> list[str]:
    return sorted({t for t in tool_ids if t in scope})


class ToolAccessRepository(ToolAccessRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def find_grants_for(
        self, user_id: int, department_ids: Sequence[str], request_id: str
    ) -> frozenset[str]:
        try:
            parts = [
                select(ToolAccessDefaultModel.tool_id.label("tool_id")),
                select(ToolAccessUserModel.tool_id.label("tool_id")).where(
                    ToolAccessUserModel.user_id == user_id
                ),
            ]
            dept_ids = [d for d in department_ids if d]
            if dept_ids:
                parts.append(
                    select(ToolAccessDepartmentModel.tool_id.label("tool_id")).where(
                        ToolAccessDepartmentModel.department_id.in_(dept_ids)
                    )
                )
            result = await self._session.execute(union(*parts))
            grants = frozenset(row[0] for row in result.all())
            self._logger.info(
                "ToolAccess find_grants_for",
                request_id=request_id, user_id=user_id,
                department_count=len(dept_ids), grant_count=len(grants),
            )
            return grants
        except Exception as e:
            self._logger.error(
                "ToolAccess find_grants_for failed", exception=e, request_id=request_id
            )
            raise

    async def list_default(self, request_id: str) -> list[str]:
        return await self._list(select(ToolAccessDefaultModel.tool_id), request_id)

    async def list_for_department(self, department_id: str, request_id: str) -> list[str]:
        return await self._list(
            select(ToolAccessDepartmentModel.tool_id).where(
                ToolAccessDepartmentModel.department_id == department_id
            ),
            request_id,
        )

    async def list_for_user(self, user_id: int, request_id: str) -> list[str]:
        return await self._list(
            select(ToolAccessUserModel.tool_id).where(
                ToolAccessUserModel.user_id == user_id
            ),
            request_id,
        )

    async def list_department_grants(
        self, department_ids: Sequence[str], request_id: str
    ) -> dict[str, list[str]]:
        dept_ids = [d for d in department_ids if d]
        if not dept_ids:
            return {}
        try:
            stmt = select(
                ToolAccessDepartmentModel.tool_id, ToolAccessDepartmentModel.department_id
            ).where(ToolAccessDepartmentModel.department_id.in_(dept_ids))
            result = await self._session.execute(stmt)
            grouped: dict[str, list[str]] = {}
            for tool_id, dept_id in result.all():
                grouped.setdefault(tool_id, []).append(dept_id)
            return grouped
        except Exception as e:
            self._logger.error(
                "ToolAccess list_department_grants failed", exception=e, request_id=request_id
            )
            raise

    async def replace_default(
        self, tool_ids: Iterable[str], *, scope: frozenset[str],
        granted_by: int | None, request_id: str,
    ) -> None:
        ids = _in_scope(tool_ids, scope)
        await self._replace(
            delete(ToolAccessDefaultModel).where(ToolAccessDefaultModel.tool_id.in_(scope)),
            [ToolAccessDefaultModel(tool_id=t, granted_by=granted_by) for t in ids],
            request_id, subject="default",
        )

    async def replace_for_department(
        self, department_id: str, tool_ids: Iterable[str], *,
        scope: frozenset[str], granted_by: int | None, request_id: str,
    ) -> None:
        ids = _in_scope(tool_ids, scope)
        await self._replace(
            delete(ToolAccessDepartmentModel).where(
                ToolAccessDepartmentModel.department_id == department_id,
                ToolAccessDepartmentModel.tool_id.in_(scope),
            ),
            [
                ToolAccessDepartmentModel(
                    tool_id=t, department_id=department_id, granted_by=granted_by
                )
                for t in ids
            ],
            request_id, subject=f"department:{department_id}",
        )

    async def replace_for_user(
        self, user_id: int, tool_ids: Iterable[str], *,
        scope: frozenset[str], granted_by: int | None, request_id: str,
    ) -> None:
        ids = _in_scope(tool_ids, scope)
        await self._replace(
            delete(ToolAccessUserModel).where(
                ToolAccessUserModel.user_id == user_id,
                ToolAccessUserModel.tool_id.in_(scope),
            ),
            [ToolAccessUserModel(tool_id=t, user_id=user_id, granted_by=granted_by) for t in ids],
            request_id, subject=f"user:{user_id}",
        )

    async def _list(self, stmt, request_id: str) -> list[str]:
        try:
            result = await self._session.execute(stmt)
            return sorted(row[0] for row in result.all())
        except Exception as e:
            self._logger.error("ToolAccess list failed", exception=e, request_id=request_id)
            raise

    async def _replace(self, delete_stmt, models: list, request_id: str, *, subject: str) -> None:
        try:
            await self._session.execute(delete_stmt)
            self._session.add_all(models)
            await self._session.flush()
            self._logger.info(
                "ToolAccess replace", request_id=request_id,
                subject=subject, count=len(models),
            )
        except Exception as e:
            self._logger.error(
                "ToolAccess replace failed", exception=e,
                request_id=request_id, subject=subject,
            )
            raise
