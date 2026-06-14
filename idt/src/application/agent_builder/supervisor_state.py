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
