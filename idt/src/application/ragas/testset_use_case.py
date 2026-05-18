"""테스트셋 CRUD UseCase."""
import uuid
from datetime import datetime, timezone

from src.application.ragas.schemas import TestsetResponse, TestsetUploadRequest
from src.domain.ragas.interfaces import EvaluationRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class TestsetUseCase:
    def __init__(
        self,
        repository: EvaluationRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def create(
        self, request: TestsetUploadRequest, request_id: str
    ) -> TestsetResponse:
        testset_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        testset = {
            "id": testset_id,
            "name": request.name,
            "description": request.description,
            "cases": request.cases,
            "case_count": len(request.cases),
            "created_at": now,
        }
        await self._repository.save_testset(testset, request_id)

        return TestsetResponse(
            id=testset_id,
            name=request.name,
            description=request.description,
            case_count=len(request.cases),
            created_at=now,
        )

    async def list_all(
        self, limit: int, offset: int, request_id: str
    ) -> tuple[list[TestsetResponse], int]:
        items, total = await self._repository.list_testsets(limit, offset, request_id)
        responses = [
            TestsetResponse(
                id=item["id"],
                name=item["name"],
                description=item.get("description", ""),
                case_count=item["case_count"],
                created_at=item["created_at"],
            )
            for item in items
        ]
        return responses, total

    async def get_detail(
        self, testset_id: str, request_id: str
    ) -> TestsetResponse | None:
        item = await self._repository.get_testset(testset_id, request_id)
        if item is None:
            return None
        return TestsetResponse(
            id=item["id"],
            name=item["name"],
            description=item.get("description", ""),
            case_count=item["case_count"],
            created_at=item["created_at"],
        )

    async def delete(self, testset_id: str, request_id: str) -> bool:
        return await self._repository.delete_testset(testset_id, request_id)
