"""Tool name → RunPurpose 매핑.

AGENT-OBS-002 (M2) Design §4-3 매핑 표 코드화.
UsageCallback.on_tool_start에서 호출되어 set_purpose에 전달된다.

매칭 정책:
- 정규식 기반, 우선순위 순서대로 첫 매칭 적용
- 케이스 무관 (re.IGNORECASE)
- 매칭 실패 시 RunPurpose.OTHER 반환 (절대 raise 안함 — best-effort)
"""
import re
from typing import Final, Optional

from src.domain.agent_run.value_objects import RunPurpose

_RULES: Final[list[tuple[re.Pattern[str], RunPurpose]]] = [
    # QUERY_REWRITE — WORKER보다 먼저 매칭되어야 함
    (re.compile(r"query_rewrit", re.IGNORECASE), RunPurpose.QUERY_REWRITE),
    # RERANK — WORKER 패턴(rag/retrieval)과 겹칠 수 있어 먼저 매칭
    (re.compile(r"^(reranker|compressor)", re.IGNORECASE), RunPurpose.RERANK),
    # HALLUCINATION
    (re.compile(r"hallucination", re.IGNORECASE), RunPurpose.HALLUCINATION_CHECK),
    # MCP → OTHER (사내 부서 등록 툴)
    (re.compile(r"^mcp_", re.IGNORECASE), RunPurpose.OTHER),
    # WORKER (사용자 의도 직접 처리 툴들)
    (
        re.compile(
            r"(rag_search|retrieval_|hybrid_search|internal_document_search)",
            re.IGNORECASE,
        ),
        RunPurpose.WORKER,
    ),
    (
        re.compile(r"(tavily_|web_search|perplexity)", re.IGNORECASE),
        RunPurpose.WORKER,
    ),
    (re.compile(r"^excel_export", re.IGNORECASE), RunPurpose.WORKER),
    (re.compile(r"^python_code_executor", re.IGNORECASE), RunPurpose.WORKER),
]


def infer_tool_purpose(tool_name: Optional[str]) -> RunPurpose:
    """tool_name 문자열로부터 RunPurpose를 추론한다.

    매칭 실패 / None / 빈 문자열은 RunPurpose.OTHER를 반환한다.
    이 함수는 어떤 입력에도 raise하지 않는다 (best-effort 보장).
    """
    if not tool_name:
        return RunPurpose.OTHER
    for pattern, purpose in _RULES:
        if pattern.search(tool_name):
            return purpose
    return RunPurpose.OTHER
