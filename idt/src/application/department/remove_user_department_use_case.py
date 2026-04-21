"""RemoveUserDepartmentUseCase: 사용자-부서 해제."""
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class RemoveUserDepartmentUseCase:
    def __init__(
        self,
        repository: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self, user_id: int, department_id: str, request_id: str
    ) -> None:
        self._logger.info(
            "RemoveUserDepartmentUseCase start",
            request_id=request_id,
            user_id=user_id,
        )
        try:
            await self._repository.remove_user(user_id, department_id, request_id)
            self._logger.info(
                "RemoveUserDepartmentUseCase done", request_id=request_id
            )
        except Exception as e:
            self._logger.error(
                "RemoveUserDepartmentUseCase failed", exception=e, request_id=request_id
            )
            raise
