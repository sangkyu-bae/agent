"""같은 워커 연속 호출 판정 (claude-agent-e2e-fixes Design §4.2).

2026-11-19 실 E2E: 분석 워커가 600행을 직접 세며 매번 다른 수치를 냈고, 수퍼바이저가
"수치 불일치"를 이유로 같은 워커를 반복 호출했다(LLM 분석 13회). 반복 한도
(max_iterations) 외에 진척 없는 반복을 멈추는 장치가 없었다.

"연속"만 센다 — 다른 워커가 끼면 리셋되므로 검색 → 분석 → 검색 같은 정상 재호출은
막지 않는다. limit 0 은 비활성(기존 동작과 동일).
"""
_TERMINAL = ("", "__end__")


def next_repeat_state(
    prev_worker: str, prev_count: int, routed_worker: str,
) -> tuple[str, int]:
    """라우팅 후 (repeat_worker_id, repeat_worker_count). 종료 라우팅은 ("", 0)."""
    if routed_worker in _TERMINAL:
        return "", 0
    if routed_worker == prev_worker:
        return routed_worker, prev_count + 1
    return routed_worker, 1


def repeat_exhausted(worker: str, repeat_worker: str, count: int, limit: int) -> bool:
    """limit>0 이고 같은 워커를 이미 limit 회 연속 호출했는가."""
    if limit <= 0 or not worker or worker in _TERMINAL:
        return False
    return worker == repeat_worker and count >= limit
