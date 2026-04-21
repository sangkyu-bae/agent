"""UpdateDepartmentUseCase: 부서 수정."""
from src.application.department.schemas import DepartmentResponse, UpdateDepartmentRequest
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class UpdateDepartmentUseCase:
    def __init__(
        self,
        repository: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self,
        dept_id: str,
        request: UpdateDepartmentRequest,
        request_id: str,
    ) -> DepartmentResponse:
        self._logger.info("UpdateDepartmentUseCase start", request_id=request_id)
        try:
            dept = await self._repository.find_by_id(dept_id, request_id)
            if dept is None:
                raise ValueError(f"부서를 찾을 수 없습니다: {dept_id}")

            if request.name is not None:
                dept.name = request.name
            if request.description is not None:
                dept.description = request.description

            updated = await self._repository.update(dept, request_id)
            self._logger.info("UpdateDepartmentUseCase done", request_id=request_id)
            return DepartmentResponse(
                id=updated.id,
                name=updated.name,
                description=updated.description,
                created_at=updated.created_at.isoformat(),
                updated_at=updated.updated_at.isoformat(),
            )
        except Exception as e:
            self._logger.error(
                "UpdateDepartmentUseCase failed", exception=e, request_id=request_id
            )
            raise
