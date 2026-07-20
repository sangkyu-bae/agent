"""MemoryRepository — agent_memory 테이블 CRUD (agent-memory Design §3-2).

SearchHistoryRepository 경량 패턴: (session, logger) 주입, flush까지만 수행.
commit/rollback은 세션 컨텍스트(라우터 DI / session_factory)가 담당한다.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.memory.entity import Memory, MemoryScope, MemoryStatus, MemoryType
from src.domain.memory.interfaces import MemoryRepositoryInterface
from src.infrastructure.memory.models import MemoryModel


class MemoryRepository(MemoryRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, memory: Memory, request_id: str) -> Memory:
        model = MemoryModel(
            scope=memory.scope.value,
            user_id=memory.user_id,
            tier=memory.tier,
            mem_type=memory.mem_type.value,
            content=memory.content,
            source_run_id=memory.source_run_id,
            confidence=memory.confidence,
            status=memory.status.value,
            expires_at=memory.expires_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_entity(model)

    async def find_by_id(self, memory_id: int, request_id: str) -> Memory | None:
        model = await self._session.get(MemoryModel, memory_id)
        return self._to_entity(model) if model is not None else None

    async def find_active_by_user(self, user_id: str, request_id: str) -> list[Memory]:
        # FR-07(org-scope): scope='user' 명시 — user_id 슬롯을 부서가 재사용하므로
        # 이 조건이 없으면 org 행(user_id=부서id)이 개인 조회에 섞인다.
        stmt = (
            select(MemoryModel)
            .where(
                MemoryModel.user_id == user_id,
                MemoryModel.scope == MemoryScope.USER.value,
                MemoryModel.status == MemoryStatus.ACTIVE.value,
            )
            .order_by(MemoryModel.updated_at.desc(), MemoryModel.id.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_entity(row) for row in rows]

    async def find_active_by_departments(
        self, dept_ids: list[str], request_id: str
    ) -> list[Memory]:
        """scope='org' AND user_id IN dept_ids AND status='active'. 빈 리스트면 []."""
        if not dept_ids:
            return []
        stmt = (
            select(MemoryModel)
            .where(
                MemoryModel.scope == MemoryScope.ORG.value,
                MemoryModel.user_id.in_(dept_ids),
                MemoryModel.status == MemoryStatus.ACTIVE.value,
            )
            .order_by(MemoryModel.updated_at.desc(), MemoryModel.id.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_entity(row) for row in rows]

    async def count_active_by_department(self, dept_id: str, request_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(MemoryModel)
            .where(
                MemoryModel.scope == MemoryScope.ORG.value,
                MemoryModel.user_id == dept_id,
                MemoryModel.status == MemoryStatus.ACTIVE.value,
            )
        )
        return (await self._session.execute(stmt)).scalar() or 0

    async def count_active_by_user(self, user_id: str, request_id: str) -> int:
        return await self.count_by_user_and_status(
            user_id, MemoryStatus.ACTIVE, request_id
        )

    async def find_by_user_and_status(
        self, user_id: str, status: MemoryStatus, request_id: str
    ) -> list[Memory]:
        stmt = (
            select(MemoryModel)
            .where(
                MemoryModel.user_id == user_id,
                MemoryModel.scope == MemoryScope.USER.value,  # org 행 배제 (FR-07)
                MemoryModel.status == status.value,
            )
            .order_by(MemoryModel.updated_at.desc(), MemoryModel.id.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_entity(row) for row in rows]

    async def count_by_user_and_status(
        self, user_id: str, status: MemoryStatus, request_id: str
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(MemoryModel)
            .where(
                MemoryModel.user_id == user_id,
                MemoryModel.scope == MemoryScope.USER.value,  # org 행 배제 (FR-07)
                MemoryModel.status == status.value,
            )
        )
        return (await self._session.execute(stmt)).scalar() or 0

    async def update(self, memory: Memory, request_id: str) -> Memory:
        model = await self._session.get(MemoryModel, memory.id)
        if model is None:
            raise ValueError("메모리를 찾을 수 없습니다.")
        model.mem_type = memory.mem_type.value
        model.content = memory.content
        # Phase 2: 승인/거부 상태 전이 — 누락 시 조용히 미저장되므로 필수
        model.status = memory.status.value
        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, memory_id: int, request_id: str) -> bool:
        model = await self._session.get(MemoryModel, memory_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    @staticmethod
    def _to_entity(model: MemoryModel) -> Memory:
        return Memory(
            id=model.id,
            scope=MemoryScope(model.scope),
            user_id=model.user_id,
            tier=model.tier,
            mem_type=MemoryType(model.mem_type),
            content=model.content,
            source_run_id=model.source_run_id,
            confidence=model.confidence,
            status=MemoryStatus(model.status),
            expires_at=model.expires_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
