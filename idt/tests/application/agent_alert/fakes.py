"""agent_alert 유스케이스 테스트용 가짜 저장소."""

from datetime import datetime

from src.domain.agent_alert.entity import AlertReceipt, AlertReceiver


class FakeReceiverRepo:
    def __init__(self, receiver: AlertReceiver | None = None) -> None:
        self.items: dict[str, AlertReceiver] = {}
        if receiver is not None:
            self.items[receiver.agent_id] = receiver
        self.saved: list[AlertReceiver] = []
        self.updated: list[AlertReceiver] = []

    async def find_by_agent_id(self, agent_id, request_id):
        return self.items.get(agent_id)

    async def save(self, receiver, request_id):
        self.items[receiver.agent_id] = receiver
        self.saved.append(receiver)

    async def update(self, receiver, request_id):
        self.items[receiver.agent_id] = receiver
        self.updated.append(receiver)


class FakeReceiptRepo:
    def __init__(self) -> None:
        self.items: list[AlertReceipt] = []

    async def add(self, receipt, request_id):
        self.items.append(receipt)

    async def exists_enqueued_since(
        self,
        receiver_id,
        group_key_hash,
        fingerprints_hash,
        since: datetime,
        request_id,
    ):
        return any(
            r.receiver_id == receiver_id
            and r.group_key_hash == group_key_hash
            and r.fingerprints_hash == fingerprints_hash
            and r.result == "enqueued"
            and r.received_at > since
            for r in self.items
        )

    async def list_recent(self, receiver_id, limit, request_id):
        rows = [r for r in self.items if r.receiver_id == receiver_id]
        return sorted(rows, key=lambda r: r.received_at, reverse=True)[:limit]


class FakeJobRepo:
    def __init__(self) -> None:
        self.jobs = []

    async def enqueue(self, job, request_id):
        self.jobs.append(job)
