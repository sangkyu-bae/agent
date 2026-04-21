"""CreateDepartmentUseCase: 부서 생성."""
import uuid
from datetime import datetime, timezone

from src.application.department.schemas import CreateDepartmentRequest, DepartmentResponse
from src.domain.department.entity import Department
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CreateDepartmentUseCase:
    def __init__(
        self,
        repository: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self, request: CreateDepartmentRequest, request_id: str
    ) -> DepartmentResponse:
        self._logger.info("CreateDepartmentUseCase start", request_id=request_id)
        try:
            existing = await self._repository.find_by_name(request.name, request_id)
            if existing is not None:
                raise ValueError(f"이미 존재하는 부서 이름입니다: {request.name}")

            now = datetime.now(timezone.utc)
            dept = Department(
                id=str(uuid.uuid4()),
                name=request.name,
                description=request.description,
                created_at=now,
                updated_at=now,
            )
            saved = await self._repository.save(dept, request_id)
            self._logger.info("CreateDepartmentUseCase done", request_id=request_id)
            return DepartmentResponse(
                id=saved.id,
                name=saved.name,
                description=saved.description,
                created_at=saved.created_at.isoformat(),
                updated_at=saved.updated_at.isoformat(),
            )
        except Exception as e:
            self._logger.error(
                "CreateDepartmentUseCase failed", exception=e, request_id=request_id
            )
            raise
