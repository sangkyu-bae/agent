"""실행 기록 → 표시용 도구 실행 내역 변환 정책.

Design Ref: agent-run-tool-trace §3.3 — 실시간과 재진입이 같은 정책을 지나 같은
내역을 만든다. 외부 의존 없는 순수 함수이며 DB·LangChain 을 모른다.
규칙의 근거는 실데이터 확인 결과 D1~D9 (Design §1.3) 다.
"""
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Optional

from src.domain.agent_run.entities import AgentRunStep, ToolCall
from src.domain.agent_run.source_policy import (
    MCP_ERROR_PREFIX,
    TOOL_SUCCESS_STATUS,
    unwrap_tool_summary,
)
from src.domain.agent_run.value_objects import NodeType

REASONING_LABEL = "판단"
UNKNOWN_MCP_LABEL = "MCP 도구"
UNNAMED_TOOL_LABEL = "도구"
UNNAMED_TOOL_NAME = "unnamed_tool"
FAILED_FALLBACK_MESSAGE = "도구 실행에 실패했습니다."
ERROR_MAX_CHARS = 200
# UsageCallback._summarize_tool_output 의 절단 길이. 이 길이면 저장 단계에서 잘린 것이다.
RESULT_STORAGE_LIMIT = 1024
_MCP_RUNTIME_PREFIX = "mcp_"
# UsageCallback 이 도구 시작 시 넣는 상태. 종료 시 SUCCESS/FAILED 로 갱신된다.
_TOOL_STARTED_STATUS = "STARTED"
# UsageCallback._summarize_tool_input 의 절단 표식 (D2 와 별개 — 1KB 초과 인자).
_ARGS_TRUNCATED_KEY = "_truncated"
_ARGS_WRAPPER_KEY = "arguments"
# D1 — 절단된 ToolMessage dump 를 벗긴 뒤 남는 꼬리.
_DUMP_TAIL_MARKER = '", "additional_kwargs"'
_SUB_AGENT_PREFIX = "sub_agent_"
_INDEX_SUFFIX = re.compile(r"_\d+$")


class ToolTraceKind(StrEnum):
    """wire 값 — 변경은 프론트 계약 변경이다."""

    REASONING = "reasoning"
    TOOL = "tool"


class ToolTraceStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    # Check G-01: 시작만 기록되고 종료 갱신이 없는 호출(갱신 실패·취소). 실패로 단정하지 않는다.
    INCOMPLETE = "incomplete"


class ToolTraceSource(StrEnum):
    INTERNAL = "internal"
    MCP = "mcp"


@dataclass(frozen=True)
class ToolDisplayInfo:
    """카탈로그에서 얻은 도구 표시 정보 (ToolCatalogLookup 산출물)."""

    display_name: str
    source: ToolTraceSource
    requires_approval: bool
    category: Optional[str]
    tool_id: Optional[str]


@dataclass(frozen=True)
class ToolTraceItem:
    seq: int
    kind: ToolTraceKind
    label: str
    worker: Optional[str] = None
    text: Optional[str] = None
    source: Optional[ToolTraceSource] = None
    status: Optional[ToolTraceStatus] = None
    requires_approval: bool = False
    duration_ms: Optional[int] = None
    input: Optional[dict] = None
    input_truncated: bool = False
    output: Optional[str] = None
    output_truncated: bool = False
    error: Optional[str] = None

    def to_payload(self) -> dict:
        """None 값과 False 플래그는 싣지 않는다 (Design §4.2)."""
        payload: dict = {"seq": self.seq, "kind": self.kind.value, "label": self.label}
        optional = {
            "worker": self.worker,
            "text": self.text,
            "source": self.source.value if self.source else None,
            "status": self.status.value if self.status else None,
            "duration_ms": self.duration_ms,
            "input": self.input,
            "output": self.output,
            "error": self.error,
        }
        payload.update({k: v for k, v in optional.items() if v is not None})
        flags = {
            "requires_approval": self.requires_approval,
            "input_truncated": self.input_truncated,
            "output_truncated": self.output_truncated,
        }
        payload.update({k: True for k, v in flags.items() if v})
        return payload


@dataclass(frozen=True)
class ToolTrace:
    items: list[ToolTraceItem]
    omitted_count: int = 0

    @property
    def tool_count(self) -> int:
        """화면 "도구 실행 내역 (N)" 의 N — 추론은 세지 않는다 (Plan FR-12)."""
        return sum(1 for i in self.items if i.kind == ToolTraceKind.TOOL)

    def to_payload(self) -> dict:
        return {
            "omitted_count": self.omitted_count,
            "items": [item.to_payload() for item in self.items],
        }


@dataclass(frozen=True)
class ToolTraceEvidence:
    tool_calls: list[ToolCall]
    steps: list[AgentRunStep]
    # 런타임 도구 이름 → 표시 정보. 카탈로그 조회 실패 시 빈 dict (이름 폴백).
    tools: dict[str, ToolDisplayInfo]


# 정렬 키: (step_index, 0=추론/1=도구, 시각, id) — Design §3.3 R-02.
_SortKey = tuple[int, int, datetime, str]


class ToolTracePolicy:
    @staticmethod
    def build(evidence: ToolTraceEvidence, *, max_items: int) -> ToolTrace:
        if not evidence.tool_calls:
            # R-10: 도구가 없으면 추론만 있어도 내역을 내지 않는다.
            return ToolTrace(items=[])
        steps = {s.id: s for s in evidence.steps}
        timeline = sorted(evidence.steps, key=lambda s: (s.started_at, s.step_index))
        entries: list[tuple[_SortKey, dict]] = []
        for step in evidence.steps:
            text = (step.output_summary or "").strip()
            if step.node_type == NodeType.SUPERVISOR and text:
                entries.append((
                    (step.step_index, 0, step.started_at, ""),
                    {"kind": ToolTraceKind.REASONING, "label": REASONING_LABEL,
                     "text": text, "worker": _worker_label(step, steps)},
                ))
        for call in evidence.tool_calls:
            step = steps.get(call.step_id or "")
            index = step.step_index if step else _fallback_index(call, timeline)
            entries.append((
                (index, 1, call.created_at, call.id),
                _tool_fields(call, evidence.tools.get(call.tool_name), step, steps),
            ))
        entries.sort(key=lambda e: e[0])
        items = [
            ToolTraceItem(seq=n, **fields)
            for n, (_, fields) in enumerate(entries, start=1)
        ]
        kept = items[:max_items]
        return ToolTrace(items=kept, omitted_count=len(items) - len(kept))


def _fallback_index(call: ToolCall, timeline: list[AgentRunStep]) -> int:
    """step 을 못 찾은 호출은 그 시각 이전에 시작한 마지막 step 뒤에 둔다 (D4)."""
    index = 0
    for step in timeline:
        if step.started_at <= call.created_at:
            index = step.step_index
        else:
            break
    return index


def _tool_fields(
    call: ToolCall,
    info: Optional[ToolDisplayInfo],
    step: Optional[AgentRunStep],
    steps: dict[str, AgentRunStep],
) -> dict:
    source = info.source if info else (
        ToolTraceSource.MCP if call.tool_name.startswith(_MCP_RUNTIME_PREFIX)
        else ToolTraceSource.INTERNAL
    )
    tool_input, input_truncated = _input(call.arguments_json)
    output = _output(call.result_summary)
    status = _status(call.status, source, output)
    succeeded = status == ToolTraceStatus.SUCCESS
    return {
        "kind": ToolTraceKind.TOOL,
        "label": _label(call.tool_name, info),
        "worker": _worker_label(step, steps) if step else None,
        "source": source,
        "status": status,
        "requires_approval": bool(info and info.requires_approval),
        "duration_ms": call.latency_ms,
        "input": tool_input,
        "input_truncated": input_truncated,
        # R-07: 성공이 아닌 항목의 결과 본문은 싣지 않는다 (실패는 error 로만).
        "output": output if succeeded else None,
        "output_truncated": succeeded and _is_truncated(call.result_summary),
        "error": (
            _error(call.error_text or output)
            if status == ToolTraceStatus.FAILED else None
        ),
    }


def _status(stored: str, source: ToolTraceSource, output: str) -> ToolTraceStatus:
    """R-06 + Check G-01 — 종료 기록이 없는 STARTED 는 실패와 구분한다."""
    if stored == _TOOL_STARTED_STATUS:
        return ToolTraceStatus.INCOMPLETE
    if stored != TOOL_SUCCESS_STATUS:
        return ToolTraceStatus.FAILED
    if source == ToolTraceSource.MCP and output.startswith(MCP_ERROR_PREFIX):
        return ToolTraceStatus.FAILED
    return ToolTraceStatus.SUCCESS


def _label(tool_name: str, info: Optional[ToolDisplayInfo]) -> str:
    """R-03 — MCP 런타임 이름은 UUID 를 담고 있어 노출하지 않는다."""
    if info and info.display_name:
        return info.display_name
    if tool_name.startswith(_MCP_RUNTIME_PREFIX):
        return UNKNOWN_MCP_LABEL
    if tool_name == UNNAMED_TOOL_NAME:
        return UNNAMED_TOOL_LABEL
    return tool_name


def _input(arguments: Optional[dict]) -> tuple[Optional[dict], bool]:
    """R-04 — D2 의 {"arguments": {...}} 래퍼와 1KB 절단 표식을 정리한다."""
    if not isinstance(arguments, dict):
        return None, False
    if arguments.get(_ARGS_TRUNCATED_KEY) is True:
        rest = {k: v for k, v in arguments.items() if k != _ARGS_TRUNCATED_KEY}
        return rest, True
    inner = arguments.get(_ARGS_WRAPPER_KEY)
    if len(arguments) == 1 and isinstance(inner, dict):
        return inner, False
    return arguments, False


def _output(summary: Optional[str]) -> str:
    """R-05 — D1 의 ToolMessage dump 를 벗기고 절단된 꼬리를 떼어 낸다."""
    text = unwrap_tool_summary(summary)
    marker = text.find(_DUMP_TAIL_MARKER)
    return text[:marker].rstrip() if marker >= 0 else text


def _is_truncated(summary: Optional[str]) -> bool:
    return len(summary or "") >= RESULT_STORAGE_LIMIT


def _error(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return (first or FAILED_FALLBACK_MESSAGE)[:ERROR_MAX_CHARS]


def _worker_label(
    step: AgentRunStep, steps: dict[str, AgentRunStep],
) -> Optional[str]:
    """R-08 — 서브에이전트 내부 step 은 최상위 조상 워커 이름을 라벨로 단다."""
    if step.depth < 1:
        return None
    seen = {step.id}
    current = step
    while current.depth >= 1:
        parent = steps.get(current.parent_step_id or "")
        if parent is None or parent.id in seen:
            return None
        seen.add(parent.id)
        current = parent
    return _normalize_worker_name(current.node_name)


def _normalize_worker_name(node_name: str) -> Optional[str]:
    name = node_name.removeprefix(_SUB_AGENT_PREFIX)
    name = _INDEX_SUFFIX.sub("", name).replace("_", " ").strip()
    return name or None
