"""MySQLBaseRepository: SQLAlchemy 비동기 공통 Repository 구현체."""
from typing import Any, Callable, Generic, Optional, Type, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mysql.interfaces import MySQLRepositoryInterface
from src.domain.mysql.schemas import MySQLPaginationParams, MySQLQueryCondition

ModelType = TypeVar("ModelType")

# 연산자 → SQLAlchemy 컬럼 표현식 변환 함수 맵
_OPERATOR_MAP: dict[str, Callable[[Any, Any], Any]] = {
    "eq":   lambda col, val: col == val,
    "ne":   lambda col, val: col != val,
    "gt":   lambda col, val: col > val,
    "lt":   lambda col, val: col < val,
    "gte":  lambda col, val: col >= val,
    "lte":  lambda col, val: col <= val,
    "like": lambda col, val: col.like(val),
    "in":   lambda col, val: col.in_(val),
}


class MySQLBaseRepository(MySQLRepositoryInterface[ModelType], Generic[ModelType]):
    """SQLAlchemy AsyncSession 기반 공통 CRUD Repository.

    사용 방법:
        class MyRepository(MySQLBaseRepository[MyModel]):
            def __init__(self, session: AsyncSession, logger: LoggerInterface):
                super().__init__(session, MyModel, logger)
    """

    def __init__(
        self,
        session: AsyncSession,
        model_class: Type[ModelType],
        logger: LoggerInterface,
    ) -> None:
        self._session = session
        self._model_class = model_class
        self._logger = logger

    async def save(self, entity: ModelType, request_id: str) -> ModelType:
        """엔티티 저장 (INSERT / UPDATE flush).

        Args:
            entity: 저장할 ORM 모델 인스턴스
            request_id: 요청 추적 ID

        Returns:
            flush + refresh 후의 엔티티
        """
        self._logger.info(
            "MySQL save start",
            request_id=request_id,
            model=self._model_class.__name__,
        )
        try:
            self._session.add(entity)
            await self._session.flush()
            await self._session.refresh(entity)
            self._logger.info("MySQL save completed", request_id=request_id)
            return entity
        except Exception as e:
            self._logger.error("MySQL save failed", exception=e, request_id=request_id)
            raise

    async def find_by_id(
        self, entity_id: int, request_id: str
    ) -> Optional[ModelType]:
        """PK로 단건 조회.

        Args:
            entity_id: 조회할 PK 값
            request_id: 요청 추적 ID

        Returns:
            찾은 엔티티 또는 None
        """
        self._logger.info(
            "MySQL find_by_id start",
            request_id=request_id,
            entity_id=entity_id,
        )
        try:
            stmt = select(self._model_class).where(
                self._model_class.id == entity_id  # type: ignore[attr-defined]
            )
            result = await self._session.execute(stmt)
            entity = result.scalar_one_or_none()
            self._logger.info(
                "MySQL find_by_id completed",
                request_id=request_id,
                found=entity is not None,
            )
            return entity
        except Exception as e:
            self._logger.error(
                "MySQL find_by_id failed", exception=e, request_id=request_id
            )
            raise

    async def find_all(
        self,
        request_id: str,
        pagination: Optional[MySQLPaginationParams] = None,
    ) -> list[ModelType]:
        """전체 조회 (페이지네이션 적용).

        Args:
            request_id: 요청 추적 ID
            pagination: limit/offset 파라미터 (기본: limit=100, offset=0)

        Returns:
            엔티티 목록
        """
        self._logger.info("MySQL find_all start", request_id=request_id)
        try:
            p = pagination or MySQLPaginationParams()
            stmt = select(self._model_class).limit(p.limit).offset(p.offset)
            result = await self._session.execute(stmt)
            entities = list(result.scalars().all())
            self._logger.info(
                "MySQL find_all completed",
                request_id=request_id,
                count=len(entities),
            )
            return entities
        except Exception as e:
            self._logger.error(
                "MySQL find_all failed", exception=e, request_id=request_id
            )
            raise

    async def find_by_conditions(
        self,
        conditions: list[MySQLQueryCondition],
        request_id: str,
        pagination: Optional[MySQLPaginationParams] = None,
    ) -> list[ModelType]:
        """조건 기반 필터 조회 (AND 결합).

        Args:
            conditions: WHERE 조건 목록 (AND로 결합)
            request_id: 요청 추적 ID
            pagination: limit/offset 파라미터

        Returns:
            조건에 맞는 엔티티 목록

        Raises:
            ValueError: 지원하지 않는 operator 사용 시
        """
        self._logger.info(
            "MySQL find_by_conditions start",
            request_id=request_id,
            conditions_count=len(conditions),
        )
        try:
            p = pagination or MySQLPaginationParams()
            stmt = select(self._model_class)
            for cond in conditions:
                op_fn = _OPERATOR_MAP.get(cond.operator)
                if op_fn is None:
                    raise ValueError(f"Unsupported operator: {cond.operator}")
                col = getattr(self._model_class, cond.field)
                stmt = stmt.where(op_fn(col, cond.value))
            stmt = stmt.limit(p.limit).offset(p.offset)
            result = await self._session.execute(stmt)
            entities = list(result.scalars().all())
            self._logger.info(
                "MySQL find_by_conditions completed",
                request_id=request_id,
                count=len(entities),
            )
            return entities
        except Exception as e:
            self._logger.error(
                "MySQL find_by_conditions failed", exception=e, request_id=request_id
            )
            raise

    async def delete(self, entity_id: int, request_id: str) -> bool:
        """PK로 단건 삭제.

        Args:
            entity_id: 삭제할 PK 값
            request_id: 요청 추적 ID

        Returns:
            삭제 성공 여부 (행이 없으면 False)
        """
        self._logger.info(
            "MySQL delete start",
            request_id=request_id,
            entity_id=entity_id,
        )
        try:
            stmt = delete(self._model_class).where(
                self._model_class.id == entity_id  # type: ignore[attr-defined]
            )
            result = await self._session.execute(stmt)
            await self._session.flush()
            deleted = result.rowcount > 0
            self._logger.info(
                "MySQL delete completed",
                request_id=request_id,
                deleted=deleted,
            )
            return deleted
        except Exception as e:
            self._logger.error(
                "MySQL delete failed", exception=e, request_id=request_id
            )
            raise

    async def count(self, request_id: str) -> int:
        """전체 건수 반환.

        Args:
            request_id: 요청 추적 ID

        Returns:
            테이블 전체 행 수
        """
        self._logger.info("MySQL count start", request_id=request_id)
        try:
            stmt = select(func.count()).select_from(self._model_class)
            result = await self._session.execute(stmt)
            total = result.scalar_one()
            self._logger.info(
                "MySQL count completed", request_id=request_id, count=total
            )
            return total
        except Exception as e:
            self._logger.error(
                "MySQL count failed", exception=e, request_id=request_id
            )
            raise

    async def exists(self, entity_id: int, request_id: str) -> bool:
        """PK 존재 여부 확인.

        Args:
            entity_id: 확인할 PK 값
            request_id: 요청 추적 ID

        Returns:
            존재하면 True, 없으면 False
        """
        self._logger.info(
            "MySQL exists start",
            request_id=request_id,
            entity_id=entity_id,
        )
        try:
            stmt = (
                select(func.count())
                .select_from(self._model_class)
                .where(
                    self._model_class.id == entity_id  # type: ignore[attr-defined]
                )
            )
            result = await self._session.execute(stmt)
            found = result.scalar_one() > 0
            self._logger.info(
                "MySQL exists completed", request_id=request_id, exists=found
            )
            return found
        except Exception as e:
            self._logger.error(
                "MySQL exists failed", exception=e, request_id=request_id
            )
            raise
