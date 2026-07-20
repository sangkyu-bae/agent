"""MemoryCrudUseCase — 사용자 메모리 생성/목록/수정/삭제 (agent-memory Design §3-3).

세션·트랜잭션은 라우터 DI가 관리하고, 여기서는 repo·정책 흐름만 제어한다.
결정 ②: 타인 소유·미존재 모두 "찾을 수 없습니다" — 라우터에서 404로 매핑(존재 은닉).
"""
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.memory.entity import Memory, MemoryScope, MemoryStatus, MemoryType
from src.domain.memory.interfaces import MemoryRepositoryInterface
from src.domain.memory.policies import MemoryPolicy

_NOT_FOUND_MSG = "메모리를 찾을 수 없습니다."


class MemoryCrudUseCase:
    def __init__(
        self,
        memory_repo: MemoryRepositoryInterface,
        logger: LoggerInterface,
        max_active_per_user: int,
        max_pending_per_user: int = 20,
    ) -> None:
        self._repo = memory_repo
        self._logger = logger
        self._max_active = max_active_per_user
        self._max_pending = max_pending_per_user

    @property
    def max_active_per_user(self) -> int:
        """개수 상한 — 목록 응답(max_count)으로 프론트에 안내된다."""
        return self._max_active

    @property
    def max_pending_per_user(self) -> int:
        """pending 상한 — status=pending 목록 응답의 max_count."""
        return self._max_pending

    async def create(
        self, user_id: str, mem_type: str, content: str, request_id: str
    ) -> Memory:
        parsed_type = self._parse_type(mem_type)
        MemoryPolicy.validate_content(content)
        current = await self._repo.count_active_by_user(user_id, request_id)
        MemoryPolicy.validate_active_count(current, self._max_active)

        memory = Memory(
            id=None,
            scope=MemoryScope.USER,
            user_id=user_id,
            tier=0,
            mem_type=parsed_type,
            content=content,
            confidence=100,
            status=MemoryStatus.ACTIVE,
        )
        saved = await self._repo.save(memory, request_id)
        self._logger.info(
            "memory created", request_id=request_id, user_id=user_id,
            memory_id=saved.id, mem_type=parsed_type.value,
        )
        return saved

    async def list_active(self, user_id: str, request_id: str) -> list[Memory]:
        return await self._repo.find_active_by_user(user_id, request_id)

    async def update(
        self,
        user_id: str,
        memory_id: int,
        mem_type: str | None,
        content: str | None,
        request_id: str,
    ) -> Memory:
        memory = await self._find_owned(user_id, memory_id, request_id)
        if mem_type is not None:
            memory.mem_type = self._parse_type(mem_type)
        if content is not None:
            MemoryPolicy.validate_content(content)
            memory.content = content
        updated = await self._repo.update(memory, request_id)
        self._logger.info(
            "memory updated", request_id=request_id, user_id=user_id,
            memory_id=memory_id,
        )
        return updated

    async def list_by_status(
        self, user_id: str, status: MemoryStatus, request_id: str
    ) -> list[Memory]:
        """상태별 본인 메모리 목록 (Phase 2 — pending 승인 대기)."""
        return await self._repo.find_by_user_and_status(user_id, status, request_id)

    async def approve(self, user_id: str, memory_id: int, request_id: str) -> Memory:
        """pending → active. 승인 시점에 active 상한을 재검증한다 (FR-07 계승)."""
        memory = await self._find_owned(user_id, memory_id, request_id)
        MemoryPolicy.validate_transition(memory)
        current = await self._repo.count_active_by_user(user_id, request_id)
        MemoryPolicy.validate_active_count(current, self._max_active)
        memory.status = MemoryStatus.ACTIVE
        updated = await self._repo.update(memory, request_id)
        self._logger.info(
            "memory approved", request_id=request_id, user_id=user_id,
            memory_id=memory_id,
        )
        return updated

    async def reject(self, user_id: str, memory_id: int, request_id: str) -> Memory:
        """pending → rejected — 거부된 후보는 재노출되지 않는다."""
        memory = await self._find_owned(user_id, memory_id, request_id)
        MemoryPolicy.validate_transition(memory)
        memory.status = MemoryStatus.REJECTED
        updated = await self._repo.update(memory, request_id)
        self._logger.info(
            "memory rejected", request_id=request_id, user_id=user_id,
            memory_id=memory_id,
        )
        return updated

    async def delete(self, user_id: str, memory_id: int, request_id: str) -> None:
        await self._find_owned(user_id, memory_id, request_id)
        await self._repo.delete(memory_id, request_id)
        self._logger.info(
            "memory deleted", request_id=request_id, user_id=user_id,
            memory_id=memory_id,
        )

    async def _find_owned(
        self, user_id: str, memory_id: int, request_id: str
    ) -> Memory:
        memory = await self._repo.find_by_id(memory_id, request_id)
        if memory is None or memory.user_id != user_id:
            raise ValueError(_NOT_FOUND_MSG)
        return memory

    @staticmethod
    def _parse_type(mem_type: str) -> MemoryType:
        try:
            return MemoryType(mem_type)
        except ValueError:
            valid = ", ".join(t.value for t in MemoryType)
            raise ValueError(f"지원하지 않는 메모리 타입입니다. (허용: {valid})")
