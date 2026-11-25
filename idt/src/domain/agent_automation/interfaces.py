"""자동 실행 바쁨 판정 포트.

Design Ref: firewall-agent design §10.3. 승인·스케줄 회차·백그라운드 잡 세 저장소
인터페이스에
추상 메서드를 더하면 기존 구현체(테스트 가짜 포함)가 모두 깨지므로, 세 테이블을
**읽기만**
하는 전용 포트를 둔다 (Design v0.2).
"""

from abc import ABC, abstractmethod
from datetime import datetime


class AgentActivityReaderInterface(ABC):
    @abstractmethod
    async def has_open_approval(self, agent_id: str, request_id: str) -> bool: ...

    @abstractmethod
    async def has_running_schedule_run(
        self, agent_id: str, started_after: datetime, request_id: str
    ) -> bool:
        """started_after 이후 시작한 status=running 회차. 그보다 오래된 것은 고아로
        본다."""
        ...

    @abstractmethod
    async def has_active_job(self, agent_id: str, request_id: str) -> bool: ...
