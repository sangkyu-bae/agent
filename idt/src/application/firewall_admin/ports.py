"""firewall_admin 포트 — 구조적 타이핑(Protocol).

Design Ref: firewall-admin-console §9.2 — infrastructure 는 application 을 import
하지 않고 메서드 형태로만 이 포트를 만족한다.
"""
from __future__ import annotations

from typing import Protocol

from src.domain.firewall_admin.models import (
    AlertRule,
    AutomationSnapshot,
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


class AutomationPort(Protocol):
    """firewall-agent design §4.4 — 보안 에이전트의 스케줄·알림 수신 상태 조회·변경.

    구현체는 요청 세션 하나로 동작한다(커밋은 get_session). 소유자 검사는 하지 않는다 —
    권한은 라우터의 require_role("admin") 이다.
    """

    async def load(self, agent_id: str) -> AutomationSnapshot | None: ...

    async def set_schedules_enabled(self, agent_id: str, enabled: bool) -> int:
        """바꾼 스케줄 수가 아니라 대상 스케줄 수(0 이면 토글할 대상 없음)."""
        ...

    async def set_alert_enabled(self, agent_id: str, enabled: bool) -> bool:
        """수신 설정이 있으면 True."""
        ...
