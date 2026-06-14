"""LangSmith trace_id / run_url 회수 헬퍼.

AGENT-OBS-001 §4-5 / §14-4:
- callback 시점이 아닌 RunAgentUseCase.execute() 마지막에 호출.
- 실패 시 (None, None) — best-effort.
"""
from typing import Optional


class TraceExtractor:
    """현재 LangSmith run의 trace_id / run_url을 회수."""

    @staticmethod
    def extract() -> tuple[Optional[str], Optional[str]]:
        try:
            from langsmith.run_helpers import get_current_run_tree
        except Exception:
            return (None, None)

        try:
            tree = get_current_run_tree()
            if tree is None:
                return (None, None)
            trace_id = (
                str(tree.trace_id) if getattr(tree, "trace_id", None) else None
            )
            run_url = getattr(tree, "url", None) or None
            return (trace_id, run_url)
        except Exception:
            return (None, None)
