"""ListDepartmentsUseCase: 부서 목록 조회."""
from src.application.department.schemas import DepartmentListResponse, DepartmentResponse
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListDepartmentsUseCase:
    def __init__(
        self,
        repository: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(self, request_id: str) -> DepartmentListResponse:
        self._logger.info("ListDepartmentsUseCase start", request_id=request_id)
        try:
            depts = await self._repository.list_all(request_id)
            self._logger.info("ListDepartmentsUseCase done", request_id=request_id)
            return DepartmentListResponse(
                departments=[
                    DepartmentResponse(
                        id=d.id,
                        name=d.name,
                        description=d.description,
                        created_at=d.created_at.isoformat(),
                        updated_at=d.updated_at.isoformat(),
                    )
                    for d in depts
                ]
            )
        except Exception as e:
            self._logger.error(
                "ListDepartmentsUseCase failed", exception=e, request_id=request_id
            )
            raise
