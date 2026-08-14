"""ToolSelectorPort — Design Ref: §4.1.

호출부는 이 Port만 알고 구현체를 모른다. 구현체를 직접 참조하는 순간
경로가 늘 때마다 배선이 반복되고 탈부착 계약이 약해진다.
"""
from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.tool_selection.schemas import SelectionResult, ToolCandidate


class ToolSelectorPort(ABC):
    """유저 질의에 맞는 도구를 골라내는 선별기."""

    @abstractmethod
    async def select(
        self,
        query: str,
        candidates: Sequence[ToolCandidate],
        *,
        required_ids: Sequence[str] = (),
        request_id: str = "",
    ) -> SelectionResult:
        """질의에 맞는 도구를 골라 SelectionResult로 반환한다.

        구현체는 다음 계약을 반드시 지킨다:

        1. **예외를 발생시키지 않는다.** 어떤 실패든 ``fallback=True`` +
           ``reason``으로 표현한다 (§6.1).
        2. ``required_ids``는 결과에 항상 포함된다 — ``candidates``에 없어도
           그대로 통과시킨다 (Plan FR-04, 회귀 방지).
        3. ``final_ids``의 순서는 ``candidates``의 원 순서를 따른다 (결정성).
        4. ``final_ids ⊆ candidates ∪ required_ids`` — 선별은 축소만 한다.
           호출부가 주지 않은 도구를 추가할 수 없다 (§7 권한 경계 불변).
        """
