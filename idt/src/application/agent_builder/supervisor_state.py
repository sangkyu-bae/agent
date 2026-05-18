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
