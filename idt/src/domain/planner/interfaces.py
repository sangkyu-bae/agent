"""PlannerInterface: 계획 생성 추상 인터페이스."""
from abc import ABC, abstractmethod

from src.domain.planner.schemas import PlanResult


class PlannerInterface(ABC):

    @abstractmethod
    async def plan(
        self,
        query: str,
        context: dict,
        request_id: str,
    ) -> PlanResult:
        """질문과 컨텍스트를 받아 실행 계획 반환."""
