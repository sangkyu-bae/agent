"""Custom Supervisor 그래프의 상태 정의."""
from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class SupervisorState(TypedDict):
    messages: Annotated[list, add_messages]

    iteration_count: int
    max_iterations: int
    token_usage: int
    token_limit: int

    next_worker: str
    last_worker_id: str
    available_workers: list[str]

    quality_gate_enabled: bool
    retry_counts: dict[str, int]
    max_retries_per_worker: int

    forced_worker: str
    skipped_workers: list[str]

    # worker-context-injection §3.1: supervisor가 선택한 워커에게 내리는 작업 지시.
    # 워커는 supervisor_prompt를 보지 못하므로 '지금 무엇을 하는가'를 여기로 받는다.
    # 빈 문자열이면 _wrap_worker가 기존 범용 문구로 폴백한다.
    worker_task: str

    # agent-recursion-limit D5: 반복 한도 도달 플래그.
    # supervisor 가드가 세우면 route_to_worker_or_final이 final_answer로 우회하고
    # final_answer는 안내 지시를, run_agent_use_case는 payload 플래그를 부착한다.
    limit_reached: bool

    # wiki-guided-routing D4: 직전 워커의 도구 오류 요약(ToolErrorPolicy). 워커 노드가
    # 매번 덮어쓰고(성공 시 ""), supervisor는 비어 있지 않을 때만 "[직전 수집 실패]"
    # 블록을 렌더한 뒤 ""로 리셋한다 — 블록은 실패 직후 결정 1회에만 나타난다.
    last_worker_error: str

    # supervisor-early-finish-fix D-02: 직전 수집 워커의 '빈 결과' 사유 요약.
    # last_worker_error 동형 — 워커가 매번 덮어쓰고(정상 시 ""), supervisor가
    # "[수집 결과 확인 필요]" 블록을 렌더한 뒤 ""로 리셋한다.
    # 도구는 성공했으나 유효 데이터가 없는 상태로, 도구 오류와 구분된다.
    last_worker_empty: str

    # supervisor-early-finish-fix D-05: FINISH 되물음 1회 기회 보유 플래그.
    # supervisor가 빈 결과 블록을 렌더할 때 True, 재진입 시 False로 소진된다.
    # route_to_worker_or_final이 읽어 __end__를 supervisor로 되돌린다.
    # 카운터가 아니라 플래그인 이유: 신호 리셋과 짝지어 1회 상한이 구조적으로
    # 보장되기 때문 (Design §2.2).
    finish_challenge_pending: bool

    quality_gate_result: str

    # analysis-node-agent: 분석 노드 입력용 첨부(엑셀 파일 경로 등).
    # 예: [{"type": "excel", "file_path": "/tmp/x.xlsx", "user_id": "u1"}]
    attachments: list[dict]

    # analysis-chart-router: 분석 직후 라우터의 판단 결과.
    # "visualize" | "text" | ""(미판단). 후속 차트 처리 노드가 이 값을 소비.
    viz_decision: str

    # supervisor-chart-builder-node: chart_builder가 생성한 Chart.js config 리스트.
    # 각 항목 = ChartConfig.model_dump(exclude_none=True) (= 프론트 ChartPayload).
    charts: list[dict]

    # supervisor-chart-builder-node: 시각화 처리 완료 플래그.
    # True면 skip_workers가 분석 워커를 제외해 supervisor 재라우팅을 결정적으로 차단.
    visualization_done: bool

    # analysis-source-preservation: 엑셀 분기 원천 데이터(파싱 dict) 전달 채널.
    # [{"origin": worker_id, "kind": "raw_source", "excel": ExcelData.to_dict()}]
    # charts 채널 동형(replace 시맨틱) — run_agent_use_case가 스냅샷 캡처에 소비.
    analysis_source: list[dict]
