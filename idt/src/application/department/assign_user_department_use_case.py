"""AssignUserDepartmentUseCase: 사용자-부서 배정."""
from datetime import datetime, timezone

from src.application.department.schemas import AssignUserDepartmentRequest
from src.domain.department.entity import UserDepartment
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class AssignUserDepartmentUseCase:
    def __init__(
        self,
        repository: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self,
        user_id: int,
        request: AssignUserDepartmentRequest,
        request_id: str,
    ) -> None:
        self._logger.info(
            "AssignUserDepartmentUseCase start",
            request_id=request_id,
            user_id=user_id,
        )
        try:
            dept = await self._repository.find_by_id(request.department_id, request_id)
            if dept is None:
                raise ValueError(f"부서를 찾을 수 없습니다: {request.department_id}")

            if request.is_primary:
                count = await self._repository.count_primary(user_id, request_id)
                if count >= 1:
                    raise ValueError("사용자당 primary 부서는 최대 1개입니다")

            ud = UserDepartment(
                user_id=user_id,
                department_id=request.department_id,
                is_primary=request.is_primary,
                created_at=datetime.now(timezone.utc),
            )
            await self._repository.assign_user(ud, request_id)
            self._logger.info(
                "AssignUserDepartmentUseCase done", request_id=request_id
            )
        except Exception as e:
            self._logger.error(
                "AssignUserDepartmentUseCase failed", exception=e, request_id=request_id
            )
            raise
