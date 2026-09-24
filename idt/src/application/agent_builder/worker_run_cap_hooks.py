"""WorkerRunCapHooks: collect 워커의 런당 실행 횟수 상한.

Design Ref: mcp-tool-category-routing §5 D-07 (FR-11)

관찰된 "MCP 스크랩 도구 4~5회 호출"의 원인 후보는 둘이었다.
  ① 워커 내부 react 루프가 도구를 반복 호출  → ToolCallLimitMiddleware (FR-10)
  ② supervisor가 같은 워커를 반복 라우팅       → 이 훅 (FR-11)
원인이 확정되기 전이므로 양쪽을 모두 봉쇄한다.

supervisor 코어는 건드리지 않는다. 기존 `skip_workers` 확장점을 쓰면
supervisor는 스킵 목록을 프롬프트의 "스킵된 워커(사용 불가)"로 이미 노출하고,
그럼에도 선택하면 `__end__`로 보낸다(supervisor_nodes 기존 동작 — D-07에서
유지하기로 결정). 종료 경로는 route_to_worker_or_final이 final_answer로
우회시키므로 답변은 보장된다.

**상한 대상은 collect 워커 한정이다 (module-3 개정).**
search 워커는 TOOL_REGISTRY가 이미 category="search"로 분류하므로, 상한을
걸면 관리자가 아무것도 지정하지 않아도 기존 검색 에이전트의 동작이 바뀐다 —
category NULL 무변화 계약(FR-14)의 취지에 어긋난다. 이번 사이클이 해결하려는
증상(스크랩 반복 호출)은 collect만으로 해소되므로 범위를 좁혔다.
"""
from __future__ import annotations

from src.application.agent_builder.search_pipeline import is_draft_output
from src.application.agent_builder.supervisor_hooks import (
    SupervisorHooks,
    is_current_turn_search_result,
)
from src.application.agent_builder.supervisor_state import SupervisorState
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class WorkerRunCapHooks:
    """기존 훅을 감싸 상한 대상 워커를 스킵 목록에 더하는 데코레이터.

    force_worker(강제 라우팅)는 손대지 않고 그대로 위임한다 — 첨부·시각화
    강제 경로의 판단 기준을 바꾸면 이 사이클 밖의 동작이 흔들린다.
    """

    def __init__(
        self,
        inner: SupervisorHooks,
        capped_worker_ids: list[str],
        logger: LoggerInterface | None = None,
    ) -> None:
        self._inner = inner
        self._capped = list(capped_worker_ids)
        self._logger = logger

    def force_worker(self, state: SupervisorState) -> str | None:
        return self._inner.force_worker(state)

    def skip_workers(self, state: SupervisorState) -> list[str]:
        skipped = list(self._inner.skip_workers(state))
        if not self._capped:
            return skipped

        executed = self._executed_worker_ids(state)
        added = [
            worker_id for worker_id in self._capped
            if worker_id in executed and worker_id not in skipped
        ]
        if added and self._logger is not None:
            self._logger.info(
                "worker run cap applied",
                capped_workers=added,
            )
        return skipped + added

    @staticmethod
    def _executed_worker_ids(state: SupervisorState) -> set[str]:
        """이번 턴에 결과를 낸 워커 id 집합.

        재주입분(이전 턴 스냅샷)은 제외한다 — data-inventory-requery D2와
        같은 판정 기준. 재주입분만 보고 워커를 막으면 이번 턴에는 수집을
        한 번도 못 하게 된다.
        """
        # action-category-compose-node D-11: 초안 규약 메시지도 실행으로 센다.
        # 재개 런은 스냅샷에서 초안 메시지를 복원하므로 같은 워커가 다시
        # 초안을 쓰고 발송을 시도하는 경로가 여기서 막힌다 (Plan SC: SC-8).
        return {
            name
            for msg in (state.get("messages") or [])
            if (is_current_turn_search_result(msg) or is_draft_output(msg))
            and (name := getattr(msg, "name", None))
        }
