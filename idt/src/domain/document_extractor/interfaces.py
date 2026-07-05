"""document_template 저장소 도메인 인터페이스 (Design §2-4/§2-5)."""
from abc import ABC, abstractmethod

from src.domain.document_extractor.schemas import DocumentTemplate


class DocumentTemplateRepositoryInterface(ABC):
    """`document_template` 영속화 계약. commit/rollback은 세션 관리자 책임."""

    @abstractmethod
    async def save(
        self, template: DocumentTemplate, request_id: str
    ) -> DocumentTemplate:
        """신규 템플릿 저장."""

    @abstractmethod
    async def find_by_id(
        self, template_id: str, request_id: str
    ) -> DocumentTemplate | None:
        """id 단건 조회 (상태 무관 — 호출부가 status 판단)."""

    @abstractmethod
    async def find_active_by_agent_worker(
        self, agent_id: str, worker_id: str, request_id: str
    ) -> DocumentTemplate | None:
        """(agent_id, worker_id)의 active 템플릿 조회 (도구당 1개 — D4 앱 레벨 정합)."""

    @abstractmethod
    async def soft_delete(self, template_id: str, request_id: str) -> None:
        """status='deleted' 처리 (원본 파일은 보관 — Plan 결정 7/8)."""

    @abstractmethod
    async def soft_delete_by_agent(self, agent_id: str, request_id: str) -> int:
        """에이전트 삭제 시 종속 템플릿 일괄 soft-delete. 처리 건수 반환."""
