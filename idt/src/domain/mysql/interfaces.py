"""MySQL 공통 Repository 추상 인터페이스."""
from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

from src.domain.mysql.schemas import MySQLPaginationParams, MySQLQueryCondition

ModelType = TypeVar("ModelType")


class MySQLRepositoryInterface(ABC, Generic[ModelType]):
    """MySQL 공통 Repository ABC.

    모든 SQLAlchemy 기반 Repository가 따라야 할 계약.
    infrastructure 의존성 없음.
    """

    @abstractmethod
    async def save(self, entity: ModelType, request_id: str) -> ModelType:
        """엔티티 저장(INSERT / UPDATE). 저장된 엔티티 반환."""

    @abstractmethod
    async def find_by_id(
        self, entity_id: int, request_id: str
    ) -> Optional[ModelType]:
        """PK로 단건 조회. 없으면 None 반환."""

    @abstractmethod
    async def find_all(
        self,
        request_id: str,
        pagination: Optional[MySQLPaginationParams] = None,
    ) -> list[ModelType]:
        """전체 조회 (페이지네이션 적용)."""

    @abstractmethod
    async def find_by_conditions(
        self,
        conditions: list[MySQLQueryCondition],
        request_id: str,
        pagination: Optional[MySQLPaginationParams] = None,
    ) -> list[ModelType]:
        """조건 기반 필터 조회 (AND 결합)."""

    @abstractmethod
    async def delete(self, entity_id: int, request_id: str) -> bool:
        """PK로 삭제. 삭제 성공 여부 반환."""

    @abstractmethod
    async def count(self, request_id: str) -> int:
        """전체 건수 반환."""

    @abstractmethod
    async def exists(self, entity_id: int, request_id: str) -> bool:
        """PK 존재 여부 확인."""
