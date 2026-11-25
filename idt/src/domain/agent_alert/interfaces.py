"""agent_alert 저장소 포트."""

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.agent_alert.entity import AlertReceipt, AlertReceiver


class AlertReceiverRepositoryInterface(ABC):
    @abstractmethod
    async def find_by_agent_id(
        self, agent_id: str, request_id: str
    ) -> AlertReceiver | None: ...

    @abstractmethod
    async def save(self, receiver: AlertReceiver, request_id: str) -> None: ...

    @abstractmethod
    async def update(self, receiver: AlertReceiver, request_id: str) -> None: ...


class AlertReceiptRepositoryInterface(ABC):
    @abstractmethod
    async def add(self, receipt: AlertReceipt, request_id: str) -> None: ...

    @abstractmethod
    async def exists_enqueued_since(
        self,
        receiver_id: str,
        group_key_hash: str,
        fingerprints_hash: str,
        since: datetime,
        request_id: str,
    ) -> bool:
        """중복 판정 — 같은 그룹·같은 발화 집합으로 since 이후 enqueued 된 수신이
        있는가."""
        ...

    @abstractmethod
    async def list_recent(
        self, receiver_id: str, limit: int, request_id: str
    ) -> list[AlertReceipt]: ...
