"""Supervisor 루프 확장을 위한 Hook 프로토콜."""
from typing import Protocol

from src.application.agent_builder.search_pipeline import (
    is_search_result,
    latest_user_question,
)
from src.application.agent_builder.supervisor_state import SupervisorState
from src.domain.visualization.policies import VisualizationRoutingPolicy


class SupervisorHooks(Protocol):
    def force_worker(self, state: SupervisorState) -> str | None: ...
    def skip_workers(self, state: SupervisorState) -> list[str]: ...


class DefaultHooks:
    def force_worker(self, state: SupervisorState) -> str | None:
        return None

    def skip_workers(self, state: SupervisorState) -> list[str]:
        return []


class AttachmentRoutingHooks:
    """분석 가능한 데이터가 있으면 분석 워커로 결정적 강제 라우팅.

    트리거 2종:
    - 엑셀 등 분석 가능한 첨부 (supervisor-attachment-routing)
    - 시각화 의도 + 수집된 검색 결과 (supervisor-viz-routing)
      → supervisor LLM이 검색 결과만으로 FINISH 해 차트 경로
        (analysis → chart_router → chart_builder)를 건너뛰는 것을 차단.

    분석 워커 1회 실행 뒤에는 강제하지 않아(루프 방지) LLM이 결과를
    종합/FINISH 하도록 둔다.
    """

    # 강제 라우팅 대상 첨부 타입 (현재 excel만; 추후 확장)
    _ROUTABLE_TYPES = ("excel",)

    def __init__(
        self,
        analysis_worker_ids: list[str],
        viz_policy: VisualizationRoutingPolicy | None = None,
    ) -> None:
        # viz_policy=None이면 시각화 의도 강제 비활성 (하위호환).
        self._analysis_worker_ids = analysis_worker_ids
        self._viz_policy = viz_policy

    def force_worker(self, state: SupervisorState) -> str | None:
        if not self._analysis_worker_ids:
            return None
        target = self._analysis_worker_ids[0]
        # 공통 가드: 분석 워커 직후 재강제 금지 + 시각화 완료 후 재강제 금지
        if state.get("last_worker_id") == target:
            return None
        if state.get("visualization_done"):
            return None
        if self._has_routable_attachment(state):
            return target
        if self._viz_intent_with_search_results(state):
            return target
        return None

    def _has_routable_attachment(self, state: SupervisorState) -> bool:
        attachments = state.get("attachments", []) or []
        return any(a.get("type") in self._ROUTABLE_TYPES for a in attachments)

    def _viz_intent_with_search_results(self, state: SupervisorState) -> bool:
        """시각화 의도 + 검색 결과 수집 완료 → 분석 강제 대상.

        검색 결과가 없으면 침묵(D3) — 데이터 없는 강제 분석은 대화 문맥
        fallback이 환각 차트를 만들 수 있어 prompt 유도에만 맡긴다.
        """
        if self._viz_policy is None:
            return False
        messages = state.get("messages", []) or []
        if not self._viz_policy.explicit_request(latest_user_question(messages)):
            return False
        return any(is_search_result(m) for m in messages)

    def skip_workers(self, state: SupervisorState) -> list[str]:
        # supervisor-chart-builder-node: 시각화 처리가 끝나면 분석 워커를 skip 처리해
        # supervisor LLM의 분석워커 재선택(무한루프)을 결정적으로 차단한다.
        if state.get("visualization_done"):
            return list(self._analysis_worker_ids)
        return []
