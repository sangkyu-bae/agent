"""firewall_admin 포트 — 구조적 타이핑(Protocol).

Design Ref: firewall-admin-console §9.2 — infrastructure 는 application 을 import
하지 않고 메서드 형태로만 이 포트를 만족한다.
"""
from __future__ import annotations

from typing import Protocol

from src.domain.firewall_admin.models import (
    AlertRule,
    BlockList,
    BlockResult,
    FwctlHealth,
    LokiLine,
    LokiSample,
    UnblockResult,
)


class FwctlPort(Protocol):
    @property
    def configured(self) -> bool: ...

    async def health(self) -> FwctlHealth: ...

    async def list_blocks(self, *, request_id: str) -> BlockList: ...

    async def block(
        self, *, ip: str, ttl_seconds: int | None, reason: str, actor: str, request_id: str
    ) -> BlockResult: ...

    async def unblock(self, *, ip: str, request_id: str) -> UnblockResult: ...


class GrafanaPort(Protocol):
    @property
    def configured(self) -> bool: ...

    async def alert_rules(self) -> tuple[AlertRule, ...]: ...

    async def loki_instant(self, query: str, *, at_ns: int) -> list[LokiSample]: ...

    async def loki_range(
        self, query: str, *, start_ns: int, end_ns: int, limit: int
    ) -> list[LokiLine]: ...
