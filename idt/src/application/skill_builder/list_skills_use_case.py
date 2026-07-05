"""ListSkillsUseCase: 내 목록(my) + 접근 가능 목록(accessible, RBAC)."""
from src.application.skill_builder.schemas import (
    ListSkillsRequest,
    ListSkillsResponse,
    to_summary,
)
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.skill_builder.interfaces import SkillRepositoryInterface


class ListSkillsUseCase:
    def __init__(
        self,
        repository: SkillRepositoryInterface,
        dept_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._dept_repo = dept_repo
        self._logger = logger

    async def execute_my(
        self, user_id: str, viewer_role: str, request_id: str
    ) -> ListSkillsResponse:
        self._logger.info("ListSkillsUseCase my", request_id=request_id)
        skills = await self._repo.list_by_user(user_id, request_id)
        summaries = [to_summary(s, user_id, viewer_role) for s in skills]
        return ListSkillsResponse(
            skills=summaries, total=len(summaries), page=1, size=len(summaries)
        )

    async def execute_accessible(
        self,
        viewer_user_id: str,
        viewer_role: str,
        request: ListSkillsRequest,
        request_id: str,
    ) -> ListSkillsResponse:
        self._logger.info(
            "ListSkillsUseCase accessible", request_id=request_id, scope=request.scope
        )
        viewer_dept_ids = await self._viewer_dept_ids(viewer_user_id, request_id)
        skills, total = await self._repo.list_accessible(
            viewer_user_id=viewer_user_id,
            viewer_department_ids=viewer_dept_ids,
            scope=request.scope,
            search=request.search,
            page=request.page,
            size=request.size,
            request_id=request_id,
        )
        summaries = [to_summary(s, viewer_user_id, viewer_role) for s in skills]
        return ListSkillsResponse(
            skills=summaries, total=total, page=request.page, size=request.size
        )

    async def _viewer_dept_ids(self, viewer_user_id: str, request_id: str) -> list[str]:
        rows = await self._dept_repo.find_departments_by_user(
            int(viewer_user_id), request_id
        )
        return [r.department_id for r in rows]
