"""ToolCandidateReaderPort — Design §2.3 / §9.1.

파이프라인이 도구 후보를 얻는 유일한 창구. 구현은 tool_catalog 를 읽는
infrastructure 어댑터다 (Do module-3).
"""
from abc import ABC, abstractmethod

from src.domain.tool_selection.schemas import ToolCandidate


class ToolCandidateReaderPort(ABC):
    """전체 활성 도구를 셀렉터 후보로 제공한다."""

    @abstractmethod
    async def list_active(self) -> tuple[ToolCandidate, ...]:
        """활성 도구 전체를 카탈로그 표기(tool_id)로 반환한다.

        구현 계약:
        1. **예외를 발생시키지 않는다** — 조회 실패는 빈 튜플 + 로그로 표현한다.
           빈 후보는 파이프라인이 "추천 없음(fallback)"으로 강하시킨다
           (degraded 경계: 사용자 지정 tool_ids 만으로도 쓸 수 있는 결과가 있다).
        2. 순서는 결정적이어야 한다 — 셀렉터 final_ids 순서의 기준이 된다.
        """
