"""테스트셋 CRUD UseCase — 소유권 스코프 포함 (eval-hub Design §2.2, A1~A5).

scope_user_id: None=admin(전체), 그 외=본인 것만. 타인/미존재는 None/False로
동일하게 응답해 라우터가 404로 은닉한다.
"""
import uuid
from datetime import datetime, timezone
from typing import Callable

from src.application.ragas.schemas import (
    TestsetDetailResponse,
    TestsetResponse,
    TestsetUploadRequest,
)
from src.domain.ragas.interfaces import EvaluationRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

# (file_bytes, filename) -> cases 리스트. 파싱 실패는 ValueError.
TestsetFileParser = Callable[[bytes, str], list[dict]]


class TestsetUseCase:
    def __init__(
        self,
        repository: EvaluationRepositoryInterface,
        logger: LoggerInterface,
        file_parser: TestsetFileParser | None = None,
    ) -> None:
        self._repository = repository
        self._logger = logger
        self._file_parser = file_parser

    async def create(
        self,
        request: TestsetUploadRequest,
        request_id: str,
        user_id: str | None = None,
    ) -> TestsetResponse:
        testset_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        testset = {
            "id": testset_id,
            "name": request.name,
            "description": request.description,
            "user_id": user_id,
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
            user_id=user_id,
        )

    async def create_from_file(
        self,
        name: str,
        description: str,
        file_bytes: bytes,
        filename: str,
        request_id: str,
        user_id: str | None = None,
    ) -> TestsetResponse:
        if self._file_parser is None:
            raise ValueError("파일 파서가 구성되지 않았습니다")
        cases = self._file_parser(file_bytes, filename)
        return await self.create(
            TestsetUploadRequest(name=name, description=description, cases=cases),
            request_id,
            user_id=user_id,
        )

    async def list_all(
        self,
        limit: int,
        offset: int,
        request_id: str,
        scope_user_id: str | None = None,
    ) -> tuple[list[TestsetResponse], int]:
        items, total = await self._repository.list_testsets(
            limit, offset, request_id, user_id=scope_user_id
        )
        responses = [
            TestsetResponse(
                id=item["id"],
                name=item["name"],
                description=item.get("description") or "",
                case_count=item["case_count"],
                created_at=item["created_at"],
                user_id=item.get("user_id"),
            )
            for item in items
        ]
        return responses, total

    async def get_detail(
        self,
        testset_id: str,
        request_id: str,
        scope_user_id: str | None = None,
    ) -> TestsetDetailResponse | None:
        item = await self._get_visible(testset_id, request_id, scope_user_id)
        if item is None:
            return None
        return TestsetDetailResponse(
            id=item["id"],
            name=item["name"],
            description=item.get("description") or "",
            case_count=item["case_count"],
            created_at=item["created_at"],
            user_id=item.get("user_id"),
            cases=item.get("cases") or [],
        )

    async def delete(
        self,
        testset_id: str,
        request_id: str,
        scope_user_id: str | None = None,
    ) -> bool:
        item = await self._get_visible(testset_id, request_id, scope_user_id)
        if item is None:
            return False
        return await self._repository.delete_testset(testset_id, request_id)

    async def _get_visible(
        self, testset_id: str, request_id: str, scope_user_id: str | None
    ) -> dict | None:
        item = await self._repository.get_testset(testset_id, request_id)
        if item is None:
            return None
        if scope_user_id is not None and item.get("user_id") != scope_user_id:
            return None  # 타인 자원 — 존재 은닉
        return item
