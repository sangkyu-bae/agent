"""DeleteDepartmentUseCase: 부서 삭제."""
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class DeleteDepartmentUseCase:
    def __init__(
        self,
        repository: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(self, dept_id: str, request_id: str) -> None:
        self._logger.info("DeleteDepartmentUseCase start", request_id=request_id)
        try:
            dept = await self._repository.find_by_id(dept_id, request_id)
            if dept is None:
                raise ValueError(f"부서를 찾을 수 없습니다: {dept_id}")
            await self._repository.delete(dept_id, request_id)
            self._logger.info("DeleteDepartmentUseCase done", request_id=request_id)
        except Exception as e:
            self._logger.error(
                "DeleteDepartmentUseCase failed", exception=e, request_id=request_id
            )
            raise
