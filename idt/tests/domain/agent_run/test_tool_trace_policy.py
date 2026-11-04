"""ToolTracePolicy — 실행 기록 → 도구 실행 내역 (agent-run-tool-trace Design §3.3).

실데이터 사실 D1~D9 (Design §1.3) 를 규칙 R-01~R-10 으로 고정한다.
"""
import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest

from src.domain.agent_run.entities import AgentRunStep, ToolCall
from src.domain.agent_run.tool_trace_policy import (
    REASONING_LABEL,
    ToolDisplayInfo,
    ToolTraceEvidence,
    ToolTraceKind,
    ToolTracePolicy,
    ToolTraceSource,
    ToolTraceStatus,
)
from src.domain.agent_run.value_objects import NodeType, RunId, StepStatus

RUN = RunId("11111111-1111-1111-1111-111111111111")
T0 = datetime(2026, 11, 3, tzinfo=timezone.utc)
MCP_NAME = "mcp_6ea2f615_515e_4f65_aabe_388970dbafbe_list_inquiries"
MCP_INFO = ToolDisplayInfo(
    display_name="list_inquiries", source=ToolTraceSource.MCP,
    requires_approval=False, category=None,
    tool_id="mcp:6ea2f615-515e-4f65-aabe-388970dbafbe:list_inquiries",
)
WIKI_INFO = ToolDisplayInfo(
    display_name="에이전트 위키 열람", source=ToolTraceSource.INTERNAL,
    requires_approval=False, category=None, tool_id="internal:wiki_read",
)


def _step(
    id_: str,
    index: int,
    node_name: str = "worker",
    node_type: NodeType = NodeType.WORKER,
    output: Optional[str] = None,
    started: Optional[datetime] = None,
    parent: Optional[str] = None,
    depth: int = 0,
) -> AgentRunStep:
    return AgentRunStep(
        id=id_, run_id=RUN, step_index=index, node_name=node_name,
        node_type=node_type, llm_model_id=None, status=StepStatus.SUCCESS,
        input_summary=None, output_summary=output,
        started_at=started or T0 + timedelta(seconds=index), ended_at=None,
        latency_ms=None, error_text=None, parent_step_id=parent, depth=depth,
    )


def _call(
    id_: str,
    step_id: Optional[str] = None,
    tool_name: str = "wiki_read",
    args: Optional[dict] = None,
    summary: Optional[str] = "결과",
    status: str = "SUCCESS",
    error: Optional[str] = None,
    created: Optional[datetime] = None,
    latency: Optional[int] = 10,
) -> ToolCall:
    return ToolCall(
        id=id_, run_id=RUN, step_id=step_id, tool_name=tool_name,
        llm_model_id=None, arguments_json=args, result_summary=summary,
        result_json=None, token_usage=None, total_cost_usd=None,
        latency_ms=latency, status=status, error_text=error,
        created_at=created or T0,
    )


def _build(calls, steps=(), tools=None, max_items: int = 50):
    evidence = ToolTraceEvidence(
        tool_calls=list(calls), steps=list(steps),
        tools=tools if tools is not None else {"wiki_read": WIKI_INFO, MCP_NAME: MCP_INFO},
    )
    return ToolTracePolicy.build(evidence, max_items=max_items)


class TestReasoning:
    """R-01 — supervisor step 의 output_summary 만 추론이다 (D5)."""

    def test_supervisor_summary_becomes_reasoning_item(self) -> None:
        steps = [
            _step("s1", 1, "supervisor", NodeType.SUPERVISOR, output=" 위키를 읽겠습니다 "),
            _step("s2", 2, "wiki_read_worker"),
        ]
        trace = _build([_call("t1", "s2")], steps)
        first = trace.items[0]
        assert (first.kind, first.label, first.text) == (
            ToolTraceKind.REASONING, REASONING_LABEL, "위키를 읽겠습니다",
        )

    def test_other_node_summaries_are_not_reasoning(self) -> None:
        steps = [
            _step("g", 1, "prompt_guard", NodeType.OTHER, output="tier=PASS enforced=false"),
            _step("w", 2, "wiki_read_worker", output="도구 호출 1회"),
            _step("q", 3, "quality_gate", NodeType.GATE, output='{"next_worker": ""}'),
        ]
        trace = _build([_call("t1", "w")], steps)
        assert [i.kind for i in trace.items] == [ToolTraceKind.TOOL]

    def test_empty_supervisor_summary_is_skipped(self) -> None:
        steps = [_step("s1", 1, "supervisor", NodeType.SUPERVISOR, output="  "),
                 _step("w", 2)]
        assert [i.kind for i in _build([_call("t1", "w")], steps).items] == [ToolTraceKind.TOOL]


class TestOrdering:
    """R-02 — step_index 기준. 초 단위 시각만으로는 순서가 안 선다 (D9)."""

    def test_reasoning_and_tools_interleave_by_step_index(self) -> None:
        steps = [
            _step("s1", 1, "supervisor", NodeType.SUPERVISOR, output="A"),
            _step("w1", 2),
            _step("s2", 3, "supervisor", NodeType.SUPERVISOR, output="B"),
            _step("w2", 4),
        ]
        # 같은 초에 기록되어도 step_index 가 순서를 정한다.
        calls = [_call("t2", "w2", created=T0), _call("t1", "w1", created=T0)]
        trace = _build(calls, steps)
        assert [(i.seq, i.text or i.label) for i in trace.items] == [
            (1, "A"), (2, "에이전트 위키 열람"), (3, "B"), (4, "에이전트 위키 열람"),
        ]

    def test_calls_in_same_step_order_by_time_then_id(self) -> None:
        steps = [_step("w", 1)]
        calls = [
            _call("b", "w", tool_name="tool_b", created=T0 + timedelta(seconds=1)),
            _call("c", "w", tool_name="tool_c", created=T0),
            _call("a", "w", tool_name="tool_a", created=T0),
        ]
        trace = _build(calls, steps, tools={})
        assert [(i.seq, i.label) for i in trace.items] == [
            (1, "tool_a"), (2, "tool_c"), (3, "tool_b"),
        ]

    def test_call_without_step_falls_back_to_time(self) -> None:
        # D4: tavily_search 는 step_id 가 NULL 이었다.
        steps = [
            _step("s1", 1, "supervisor", NodeType.SUPERVISOR, output="A", started=T0),
            _step("s2", 2, "supervisor", NodeType.SUPERVISOR, output="B",
                  started=T0 + timedelta(seconds=10)),
        ]
        orphan = _call("t1", None, created=T0 + timedelta(seconds=5))
        trace = _build([orphan], steps)
        assert [i.text or i.label for i in trace.items] == ["A", "에이전트 위키 열람", "B"]

    def test_call_with_unknown_step_and_no_earlier_step_goes_first(self) -> None:
        steps = [_step("s1", 1, "supervisor", NodeType.SUPERVISOR, output="A",
                       started=T0 + timedelta(seconds=10))]
        trace = _build([_call("t1", "missing", created=T0)], steps)
        assert [i.kind for i in trace.items] == [ToolTraceKind.TOOL, ToolTraceKind.REASONING]


class TestLabels:
    """R-03 — UUID 합성명을 노출하지 않는다."""

    def test_catalog_name_is_used(self) -> None:
        item = _build([_call("t1", tool_name=MCP_NAME, summary='{"ok": true}')]).items[0]
        assert (item.label, item.source) == ("list_inquiries", ToolTraceSource.MCP)

    def test_unknown_mcp_tool_hides_runtime_name(self) -> None:
        item = _build([_call("t1", tool_name=MCP_NAME)], tools={}).items[0]
        assert (item.label, item.source) == ("MCP 도구", ToolTraceSource.MCP)

    def test_unknown_internal_tool_uses_runtime_name(self) -> None:
        item = _build([_call("t1", tool_name="tavily_search")], tools={}).items[0]
        assert (item.label, item.source) == ("tavily_search", ToolTraceSource.INTERNAL)

    def test_unnamed_tool_gets_generic_label(self) -> None:
        assert _build([_call("t1", tool_name="unnamed_tool")], tools={}).items[0].label == "도구"

    def test_requires_approval_comes_from_catalog(self) -> None:
        info = ToolDisplayInfo("submit_reply", ToolTraceSource.MCP, True, "action", None)
        item = _build([_call("t1", tool_name=MCP_NAME)], tools={MCP_NAME: info}).items[0]
        assert item.requires_approval is True


class TestInput:
    """R-04 — D2: MCP 인자는 {"arguments": {...}} 로 감싸이기도 한다."""

    def test_arguments_wrapper_is_unwrapped(self) -> None:
        call = _call("t1", args={"arguments": {"board": "loan", "limit": 1}})
        item = _build([call]).items[0]
        assert (item.input, item.input_truncated) == ({"board": "loan", "limit": 1}, False)

    def test_flat_arguments_are_kept(self) -> None:
        assert _build([_call("t1", args={"article_id": "a1"})]).items[0].input == {"article_id": "a1"}

    def test_arguments_key_with_siblings_is_not_unwrapped(self) -> None:
        args = {"arguments": {"x": 1}, "other": 2}
        assert _build([_call("t1", args=args)]).items[0].input == args

    def test_truncated_arguments_are_marked(self) -> None:
        call = _call("t1", args={"input": '{"query": "긴', "_truncated": True})
        item = _build([call]).items[0]
        assert (item.input, item.input_truncated) == ({"input": '{"query": "긴'}, True)

    def test_missing_arguments_stay_none(self) -> None:
        assert _build([_call("t1", args=None)]).items[0].input is None


class TestOutput:
    """R-05 — D1: 평문 / ToolMessage dump / 절단된 dump."""

    def test_plain_text_is_kept(self) -> None:
        item = _build([_call("t1", summary="관련 내부 문서를 찾지 못했습니다.")]).items[0]
        assert (item.output, item.output_truncated) == ("관련 내부 문서를 찾지 못했습니다.", False)

    def test_tool_message_dump_is_unwrapped(self) -> None:
        dump = json.dumps({"content": "[위키 문서: 배포]\n본문", "additional_kwargs": {},
                           "type": "tool"}, ensure_ascii=False)
        assert _build([_call("t1", summary=dump)]).items[0].output == "[위키 문서: 배포]\n본문"

    def test_truncated_dump_drops_trailing_message_fields(self) -> None:
        dump = json.dumps({"content": "짧은 본문", "additional_kwargs": {},
                           "response_metadata": {}, "type": "tool"}, ensure_ascii=False)
        cut = dump[:-8]  # 1KB 절단처럼 JSON 이 깨진 상태
        assert _build([_call("t1", summary=cut)]).items[0].output == "짧은 본문"

    def test_summary_at_storage_limit_is_marked_truncated(self) -> None:
        item = _build([_call("t1", summary="가" * 1024)]).items[0]
        assert item.output_truncated is True

    def test_summary_below_limit_is_not_truncated(self) -> None:
        assert _build([_call("t1", summary="가" * 1023)]).items[0].output_truncated is False

    def test_none_summary_gives_empty_output(self) -> None:
        assert _build([_call("t1", summary=None)]).items[0].output == ""


class TestStatus:
    """R-06/R-07 — D3: SUCCESS 인데 본문이 오류인 MCP 호출."""

    def test_success_call(self) -> None:
        item = _build([_call("t1", latency=320)]).items[0]
        assert (item.status, item.duration_ms, item.error) == (ToolTraceStatus.SUCCESS, 320, None)

    def test_failed_status_uses_error_text_first_line(self) -> None:
        call = _call("t1", status="FAILED", error="TimeoutError: 30s\nTraceback ...",
                     args={"q": "x"}, summary=None)
        item = _build([call]).items[0]
        assert (item.status, item.error, item.output, item.input) == (
            ToolTraceStatus.FAILED, "TimeoutError: 30s", None, {"q": "x"},
        )

    def test_mcp_error_body_is_failure(self) -> None:
        body = json.dumps({"content": "Error executing tool list_inquiries: 1 validation error\nboard\n  Field required"})
        item = _build([_call("t1", tool_name=MCP_NAME, summary=body)]).items[0]
        assert (item.status, item.error, item.output) == (
            ToolTraceStatus.FAILED,
            "Error executing tool list_inquiries: 1 validation error",
            None,
        )

    def test_internal_tool_with_error_like_text_is_success(self) -> None:
        item = _build([_call("t1", summary="Error executing tool 이라는 문구를 담은 위키")]).items[0]
        assert item.status == ToolTraceStatus.SUCCESS

    def test_error_text_is_capped(self) -> None:
        item = _build([_call("t1", status="FAILED", error="x" * 500)]).items[0]
        assert len(item.error) == 200

    def test_started_call_is_incomplete_not_failed(self) -> None:
        # Check G-01: 종료 기록 갱신이 실패·취소되면 STARTED 로 남는다 — 실패로 단정하지 않는다.
        call = _call("t1", status="STARTED", args={"q": "x"}, summary=None, latency=None)
        item = _build([call]).items[0]
        assert (item.status, item.error, item.output, item.input) == (
            ToolTraceStatus.INCOMPLETE, None, None, {"q": "x"},
        )
        assert item.to_payload()["status"] == "incomplete"

    def test_failed_without_error_text_gets_generic_message(self) -> None:
        item = _build([_call("t1", status="FAILED", error=None, summary=None)]).items[0]
        assert item.error == "도구 실행에 실패했습니다."


class TestWorkerLabel:
    """R-08 — 서브에이전트(depth>=1) 소속만 라벨을 단다."""

    def _sub_agent_steps(self):
        return [
            _step("root", 1, "sub_agent_[L3]_짧은_답_서브_0"),
            _step("inner_sup", 2, "supervisor", NodeType.SUPERVISOR, output="내부 판단",
                  parent="root", depth=1),
            _step("inner_w", 3, "wiki_read_worker", parent="inner_sup", depth=2),
        ]

    def test_nested_tool_and_reasoning_get_root_worker_label(self) -> None:
        trace = _build([_call("t1", "inner_w")], self._sub_agent_steps())
        assert [i.worker for i in trace.items] == ["[L3] 짧은 답 서브", "[L3] 짧은 답 서브"]

    def test_top_level_tool_has_no_worker_label(self) -> None:
        trace = _build([_call("t1", "w")], [_step("w", 1, "wiki_read_worker")])
        assert trace.items[0].worker is None

    def test_missing_parent_gives_no_label(self) -> None:
        steps = [_step("inner", 1, parent="gone", depth=1)]
        assert _build([_call("t1", "inner")], steps).items[0].worker is None

    def test_parent_cycle_gives_no_label(self) -> None:
        steps = [_step("a", 1, parent="b", depth=1), _step("b", 2, parent="a", depth=1)]
        assert _build([_call("t1", "a")], steps).items[0].worker is None


class TestLimitsAndEmpty:
    """R-10 — 상한과 빈 내역."""

    def test_no_tool_calls_gives_empty_trace_even_with_reasoning(self) -> None:
        steps = [_step("s1", 1, "supervisor", NodeType.SUPERVISOR, output="A")]
        trace = _build([], steps)
        assert (trace.items, trace.omitted_count, trace.tool_count) == ([], 0, 0)

    def test_items_over_limit_are_counted_as_omitted(self) -> None:
        steps = [_step(f"w{i}", i) for i in range(5)]
        calls = [_call(f"t{i}", f"w{i}") for i in range(5)]
        trace = _build(calls, steps, max_items=3)
        assert ([i.seq for i in trace.items], trace.omitted_count) == ([1, 2, 3], 2)

    def test_tool_count_excludes_reasoning(self) -> None:
        steps = [_step("s", 1, "supervisor", NodeType.SUPERVISOR, output="A"), _step("w", 2)]
        assert _build([_call("t1", "w"), _call("t2", "w")], steps).tool_count == 2


class TestPayload:
    """wire 형태 — None·False 키는 싣지 않는다 (Design §4.2)."""

    def test_tool_payload_shape(self) -> None:
        call = _call("t1", tool_name=MCP_NAME, args={"arguments": {"board": "loan"}},
                     summary='{"content": "{\\"total\\": 74}"}', latency=41)
        payload = _build([call]).to_payload()
        assert payload == {
            "omitted_count": 0,
            "items": [{
                "seq": 1, "kind": "tool", "label": "list_inquiries", "source": "mcp",
                "status": "success", "duration_ms": 41,
                "input": {"board": "loan"}, "output": '{"total": 74}',
            }],
        }

    def test_reasoning_payload_shape(self) -> None:
        steps = [_step("s", 1, "supervisor", NodeType.SUPERVISOR, output="판단 내용"),
                 _step("w", 2)]
        payload = _build([_call("t1", "w")], steps).to_payload()
        assert payload["items"][0] == {
            "seq": 1, "kind": "reasoning", "label": "판단", "text": "판단 내용",
        }

    def test_flags_appear_only_when_true(self) -> None:
        call = _call("t1", args={"input": "x", "_truncated": True}, summary="가" * 1024)
        item = _build([call]).to_payload()["items"][0]
        assert (item["input_truncated"], item["output_truncated"]) == (True, True)
        assert "requires_approval" not in item


def test_policy_module_has_no_infrastructure_imports() -> None:
    """Design §9.4 — 도메인 정책은 DB·LangChain 을 모른다."""
    path = Path("src/domain/agent_run/tool_trace_policy.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    forbidden = ("sqlalchemy", "langchain", "langgraph", "src.infrastructure", "src.application")
    assert not [m for m in modules if m.startswith(forbidden)]


@pytest.mark.parametrize("name,expected", [
    ("sub_agent_[L3]_짧은_답_서브_0", "[L3] 짧은 답 서브"),
    ("sub_agent_[멀티]_답변_작성자_1", "[멀티] 답변 작성자"),
    ("research_worker", "research worker"),
])
def test_worker_name_normalization(name: str, expected: str) -> None:
    steps = [_step("root", 1, name), _step("w", 2, parent="root", depth=1)]
    assert _build([_call("t1", "w")], steps).items[0].worker == expected
