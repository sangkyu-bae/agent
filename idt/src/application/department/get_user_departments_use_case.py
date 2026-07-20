"""GetUserDepartmentsUseCase — 사용자 소속 부서(id·name·is_primary) 조회.

expose-user-department Design §3-1 결정 ①: get_auth_context(권한·프로필까지 조립)로
교체하지 않고, find_departments_by_user 단일 조회 + list_all 이름 맵 1회로 경량 처리.
"""
from dataclasses import dataclass

from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


@dataclass
class DepartmentBrief:
    id: str
    name: str
    is_primary: bool


class GetUserDepartmentsUseCase:
    def __init__(
        self,
        repository: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._logger = logger

    async def execute(self, user_id: int, request_id: str) -> list[DepartmentBrief]:
        links = await self._repo.find_departments_by_user(user_id, request_id)
        if not links:
            return []
        # 부서명 해석 — 전체 부서 1회 조회 후 map (N+1 회피, 부서 수 수십 수준)
        all_depts = await self._repo.list_all(request_id)
        name_by_id = {d.id: d.name for d in all_depts}
        return [
            DepartmentBrief(
                id=link.department_id,
                name=name_by_id.get(link.department_id, link.department_id),
                is_primary=link.is_primary,
            )
            for link in links
        ]
