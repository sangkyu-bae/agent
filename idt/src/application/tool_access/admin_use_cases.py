"""관리자 도구 권한 UseCase — 기본 세트 / 부서 / 사용자 조회·전체 교체.

Design Ref: tool-access-control §4.2 (Plan FR-04)
- 검증 기준은 활성 카탈로그: 정규화 후 활성 도구가 아니면 UnknownToolIdsError(400).
  하나라도 틀리면 아무것도 저장하지 않는다.
- 교체 범위(scope)도 활성 카탈로그 — 비활성 도구에 걸린 규칙은 보존된다(§3.3).
- 조회 응답도 활성 도구만 보여 준다 (관리자 화면 체크리스트와 같은 기준).
- 대상(부서·사용자)이 없으면 LookupError(404).
"""
from collections.abc import Iterable

from src.application.tool_access.schemas import (
    DefaultToolAccessResponse,
    DepartmentToolAccessResponse,
    InheritedToolAccessResponse,
    ToolGrantSourceResponse,
    UserToolAccessResponse,
)
from src.domain.auth.entities import UserRole
from src.domain.auth.interfaces import UserRepositoryInterface
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_access.exceptions import UnknownToolIdsError
from src.domain.tool_access.interfaces import ToolAccessRepositoryInterface
from src.domain.tool_access.tool_ids import to_catalog_tool_id
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface


class _ToolAccessAdminBase:
    def __init__(
        self,
        grant_repo: ToolAccessRepositoryInterface,
        tool_catalog_repo: ToolCatalogRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._grants = grant_repo
        self._catalog = tool_catalog_repo
        self._logger = logger

    async def _active_ids(self, request_id: str) -> frozenset[str]:
        entries = await self._catalog.list_active(request_id)
        return frozenset(e.tool_id for e in entries)

    async def _validate(
        self, raw_ids: Iterable[str], request_id: str
    ) -> tuple[list[str], frozenset[str]]:
        """정규화 + 활성 카탈로그 검증. (정규화된 id 목록, 활성 범위) 반환."""
        active = await self._active_ids(request_id)
        normalized: list[str] = []
        unknown: list[str] = []
        for raw in raw_ids:
            catalog_id = to_catalog_tool_id(raw)
            if catalog_id is None or catalog_id not in active:
                unknown.append(raw)
            else:
                normalized.append(catalog_id)
        if unknown:
            self._logger.warning(
                "ToolAccess replace rejected — unknown tool ids",
                request_id=request_id, unknown_count=len(unknown),
            )
            raise UnknownToolIdsError(unknown)
        return sorted(set(normalized)), active

    @staticmethod
    def _visible(ids: Iterable[str], active: frozenset[str]) -> list[str]:
        return sorted(t for t in set(ids) if t in active)


class DefaultToolAccessUseCase(_ToolAccessAdminBase):
    async def get(self, request_id: str) -> DefaultToolAccessResponse:
        active = await self._active_ids(request_id)
        stored = await self._grants.list_default(request_id)
        return DefaultToolAccessResponse(tool_ids=self._visible(stored, active))

    async def replace(
        self, tool_ids: Iterable[str], *, granted_by: int | None, request_id: str
    ) -> DefaultToolAccessResponse:
        ids, scope = await self._validate(tool_ids, request_id)
        await self._grants.replace_default(
            ids, scope=scope, granted_by=granted_by, request_id=request_id
        )
        self._logger.info(
            "ToolAccess default replaced", request_id=request_id,
            count=len(ids), granted_by=granted_by,
        )
        return await self.get(request_id)


class DepartmentToolAccessUseCase(_ToolAccessAdminBase):
    def __init__(
        self,
        grant_repo: ToolAccessRepositoryInterface,
        tool_catalog_repo: ToolCatalogRepositoryInterface,
        department_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        super().__init__(grant_repo, tool_catalog_repo, logger)
        self._departments = department_repo

    async def _require_department(self, department_id: str, request_id: str):
        dept = await self._departments.find_by_id(department_id, request_id)
        if dept is None:
            raise LookupError(f"부서를 찾을 수 없습니다: {department_id}")
        return dept

    async def get(
        self, department_id: str, request_id: str
    ) -> DepartmentToolAccessResponse:
        dept = await self._require_department(department_id, request_id)
        active = await self._active_ids(request_id)
        direct = await self._grants.list_for_department(department_id, request_id)
        default = await self._grants.list_default(request_id)
        return DepartmentToolAccessResponse(
            department_id=dept.id,
            department_name=dept.name,
            tool_ids=self._visible(direct, active),
            default_tool_ids=self._visible(default, active),
        )

    async def replace(
        self, department_id: str, tool_ids: Iterable[str], *,
        granted_by: int | None, request_id: str,
    ) -> DepartmentToolAccessResponse:
        await self._require_department(department_id, request_id)
        ids, scope = await self._validate(tool_ids, request_id)
        await self._grants.replace_for_department(
            department_id, ids, scope=scope, granted_by=granted_by, request_id=request_id
        )
        self._logger.info(
            "ToolAccess department replaced", request_id=request_id,
            department_id=department_id, count=len(ids), granted_by=granted_by,
        )
        return await self.get(department_id, request_id)


class UserToolAccessUseCase(_ToolAccessAdminBase):
    def __init__(
        self,
        grant_repo: ToolAccessRepositoryInterface,
        tool_catalog_repo: ToolCatalogRepositoryInterface,
        user_repo: UserRepositoryInterface,
        department_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        super().__init__(grant_repo, tool_catalog_repo, logger)
        self._users = user_repo
        self._departments = department_repo

    async def _require_user(self, user_id: int):
        user = await self._users.find_by_id(user_id)
        if user is None:
            raise LookupError(f"사용자를 찾을 수 없습니다: {user_id}")
        return user

    async def get(self, user_id: int, request_id: str) -> UserToolAccessResponse:
        user = await self._require_user(user_id)
        active = await self._active_ids(request_id)
        direct = await self._grants.list_for_user(user_id, request_id)

        sources: dict[str, list[ToolGrantSourceResponse]] = {}
        for tool_id in self._visible(await self._grants.list_default(request_id), active):
            sources.setdefault(tool_id, []).append(ToolGrantSourceResponse(kind="default"))

        memberships = await self._departments.find_departments_by_user(user_id, request_id)
        dept_ids = [m.department_id for m in memberships]
        names: dict[str, str] = {}
        for dept_id in dept_ids:
            dept = await self._departments.find_by_id(dept_id, request_id)
            if dept is not None:
                names[dept_id] = dept.name
        dept_grants = await self._grants.list_department_grants(dept_ids, request_id)
        order = {d: i for i, d in enumerate(dept_ids)}
        for tool_id, granted_depts in dept_grants.items():
            if tool_id not in active:
                continue
            for dept_id in sorted(granted_depts, key=lambda d: order.get(d, len(order))):
                sources.setdefault(tool_id, []).append(ToolGrantSourceResponse(
                    kind="department", department_id=dept_id,
                    department_name=names.get(dept_id),
                ))

        return UserToolAccessResponse(
            user_id=user_id,
            is_admin=user.role == UserRole.ADMIN,
            tool_ids=self._visible(direct, active),
            inherited=[
                InheritedToolAccessResponse(tool_id=t, sources=sources[t])
                for t in sorted(sources)
            ],
        )

    async def replace(
        self, user_id: int, tool_ids: Iterable[str], *,
        granted_by: int | None, request_id: str,
    ) -> UserToolAccessResponse:
        await self._require_user(user_id)
        ids, scope = await self._validate(tool_ids, request_id)
        await self._grants.replace_for_user(
            user_id, ids, scope=scope, granted_by=granted_by, request_id=request_id
        )
        self._logger.info(
            "ToolAccess user replaced", request_id=request_id,
            user_id=user_id, count=len(ids), granted_by=granted_by,
        )
        return await self.get(user_id, request_id)
