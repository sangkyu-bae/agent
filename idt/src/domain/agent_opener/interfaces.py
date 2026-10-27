"""AgentOpenerRepositoryInterface: agent_opener 저장소 추상화.

Design Ref: agent-opener §3.4. 반환형은 텍스트 배열 — 모든 소비자가 텍스트만 쓴다.
"""
from abc import ABC, abstractmethod


class AgentOpenerRepositoryInterface(ABC):

    @abstractmethod
    async def list_by_agent_id(
        self, agent_id: str, request_id: str
    ) -> list[str]:
        """에이전트의 오프너 텍스트 목록 (sort_order ASC). 없으면 []."""

    @abstractmethod
    async def list_by_agent_ids(
        self, agent_ids: list[str], request_id: str
    ) -> dict[str, list[str]]:
        """배치 1쿼리. 빈 입력이면 쿼리 없이 {}. 오프너 없는 agent_id는 키 부재."""

    @abstractmethod
    async def replace(
        self, agent_id: str, texts: list[str], request_id: str
    ) -> list[str]:
        """목표 상태 전체 교체: DELETE agent_id 전부 → INSERT enumerate(texts).

        commit/rollback 호출 금지 — 세션 미들웨어가 트랜잭션을 관리한다.
        """
