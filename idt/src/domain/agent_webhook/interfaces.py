"""agent-webhook 저장소·발송기 인터페이스."""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.agent_webhook.entity import AgentWebhook, WebhookDelivery


class AgentWebhookRepositoryInterface(ABC):
    @abstractmethod
    async def find_by_agent_id(
        self, agent_id: str, request_id: str
    ) -> AgentWebhook | None: ...

    @abstractmethod
    async def insert(self, webhook: AgentWebhook, request_id: str) -> None: ...

    @abstractmethod
    async def update(self, webhook: AgentWebhook, request_id: str) -> None: ...

    @abstractmethod
    async def delete(self, agent_id: str, request_id: str) -> None: ...


class AgentWebhookDeliveryRepositoryInterface(ABC):
    """발송 이력 저장소 — 불변 레코드 (insert·조회만, D20)."""

    @abstractmethod
    async def insert(
        self, delivery: WebhookDelivery, request_id: str
    ) -> None: ...

    @abstractmethod
    async def list_by_agent(
        self, agent_id: str, limit: int, request_id: str
    ) -> list[WebhookDelivery]: ...


@dataclass
class OutboundResult:
    """발송기 시도 결과 — delivery 기록의 원자료.

    Design §4-3은 application DTO로 표기했으나 domain 인터페이스 반환 타입이므로
    레이어 규칙(domain → application 참조 금지)상 domain에 정의한다.
    """

    success: bool
    status_code: int | None
    attempts: int
    error: str | None
    duration_ms: int


class OutboundSenderInterface(ABC):
    @abstractmethod
    async def send(
        self, url: str, body: bytes, headers: dict, request_id: str
    ) -> OutboundResult: ...
