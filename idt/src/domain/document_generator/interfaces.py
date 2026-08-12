"""document_generation_type 저장소 도메인 인터페이스 (doc-generator Design §4-1)."""
from abc import ABC, abstractmethod

from src.domain.document_generator.schemas import DocumentGenerationType


class DocumentGenerationTypeRepositoryInterface(ABC):
    """`document_generation_type` 영속화 계약. commit/rollback은 세션 관리자 책임."""

    @abstractmethod
    async def save(
        self, gen_type: DocumentGenerationType, request_id: str
    ) -> DocumentGenerationType:
        """신규 문서 유형 저장."""

    @abstractmethod
    async def find_by_id(
        self, type_id: str, request_id: str
    ) -> DocumentGenerationType | None:
        """id 단건 조회 (상태 무관 — 호출부가 status 판단)."""

    @abstractmethod
    async def find_active_by_agent_worker(
        self, agent_id: str, worker_id: str, request_id: str
    ) -> DocumentGenerationType | None:
        """(agent_id, worker_id)의 active 유형 조회 (도구당 1개 — 앱 레벨 정합)."""

    @abstractmethod
    async def soft_delete(self, type_id: str, request_id: str) -> None:
        """status='deleted' 처리."""

    @abstractmethod
    async def soft_delete_by_agent(self, agent_id: str, request_id: str) -> int:
        """에이전트 삭제 시 종속 유형 일괄 soft-delete. 처리 건수 반환."""
