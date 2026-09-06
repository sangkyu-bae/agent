"""collect 노드 단위 테스트.

Design Ref: mcp-tool-category-routing §2.2 / §6.1 (FR-05~FR-09)

핵심 계약 4가지를 고정한다.
  ① 도구는 '정확히 1회' 호출된다 (react 루프 없음 — 4~5회 호출의 직접 해소)
  ② 산출은 도구 원본이지 워커 LLM의 종합문이 아니다 (분석 혼입 방지)
  ③ 모든 실패 분기에서 예외가 그래프로 전파되지 않는다
  ④ 어떤 분기에서도 is_search_result() 판정을 통과하는 메시지 1개를 반환한다
"""
import ast
import io
import json
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.collect_pipeline import create_collect_node
from src.application.agent_builder.search_pipeline import is_search_result
from src.domain.agent_builder.policies import CollectPipelinePolicy
from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy

_SCHEMA = {
    "type": "object",
    "properties": {"url": {"type": "string"}},
    "required": ["url"],
}


class FakeTool:
    """MCP 어댑터를 모사 — mcp_tool_name / mcp_input_schema 보유."""

    def __init__(self, result="수집 원본 본문", raises=None, schema=_SCHEMA):
        self.name = "scrape"
        self.description = "웹 페이지를 수집합니다"
        self.mcp_tool_name = "scrape"
        self.mcp_input_schema = schema
        self.calls: list = []
        self._result = result
        self._raises = raises

    async def ainvoke(self, payload):
        self.calls.append(payload)
        if self._raises is not None:
            raise self._raises
        return self._result


class PlainTool:
    """내부 도구를 모사 — MCP 래핑 없음."""

    def __init__(self, result="내부 결과"):
        self.name = "internal_tool"
        self.description = "내부 도구"
        self.args_schema = None
        self.mcp_input_schema = _SCHEMA
        self.calls: list = []
        self._result = result

    async def ainvoke(self, payload):
        self.calls.append(payload)
        return self._result


class FakeStructured:
    def __init__(self, outputs, raises=None):
        self._outputs = list(outputs)
        self._raises = raises

    async def ainvoke(self, _messages):
        if self._raises is not None:
            raise self._raises
        return self._outputs.pop(0)


class FakeLLM:
    """with_structured_output 1회 + ainvoke(압축) 호출 횟수를 계측한다."""

    def __init__(self, structured_outputs=(), structured_raises=None,
                 compress_text="압축본"):
        self._structured_outputs = structured_outputs
        self._structured_raises = structured_raises
        self._compress_text = compress_text
        self.structured_calls = 0
        self.compress_calls = 0

    def with_structured_output(self, _schema):
        self.structured_calls += 1
        return FakeStructured(self._structured_outputs, self._structured_raises)

    async def ainvoke(self, _messages):
        self.compress_calls += 1
        return AIMessage(content=self._compress_text)


def _args_out(arguments: dict, grounded=True, missing=""):
    out = MagicMock()
    out.arguments_json = json.dumps(arguments)
    out.grounded = grounded
    out.missing = missing
    return out


def _state(question="이 페이지 수집해줘 https://real.example-site.co.kr/a"):
    return {
        "messages": [HumanMessage(content=question)],
        "token_usage": 0,
    }


def _make_node(tool, llm, policy=None):
    return create_collect_node(
        worker_id="scrape_worker",
        tool=tool,
        pipeline_llm=llm,
        policy=policy or CollectPipelinePolicy(),
        logger=MagicMock(),
    )


def _body(result: dict) -> str:
    return result["messages"][0].content


class TestCollectSingleShot:
    @pytest.mark.asyncio
    async def test_tool_invoked_exactly_once(self):
        """FR-05 / SUCCESS: 워커 1회 실행당 도구 호출 1회."""
        tool = FakeTool()
        llm = FakeLLM(structured_outputs=[_args_out({"url": "https://a.kr/x"})])
        node = _make_node(tool, llm)

        await node(_state())

        assert len(tool.calls) == 1

    @pytest.mark.asyncio
    async def test_llm_called_once_when_no_compression(self):
        """§3.2 성능: 인자 생성 1회 + 조건부 압축 0회 = LLM 2회 미만."""
        tool = FakeTool(result="짧은 결과")
        llm = FakeLLM(structured_outputs=[_args_out({"url": "https://a.kr/x"})])
        node = _make_node(tool, llm)

        await node(_state())

        assert llm.structured_calls == 1
        assert llm.compress_calls == 0

    @pytest.mark.asyncio
    async def test_mcp_tool_payload_is_wrapped_in_arguments(self):
        """MCPToolAdapter.args_schema는 {arguments: dict} — 래핑해서 호출해야 한다."""
        tool = FakeTool()
        llm = FakeLLM(structured_outputs=[_args_out({"url": "https://a.kr/x"})])
        node = _make_node(tool, llm)

        await node(_state())

        assert tool.calls[0] == {"arguments": {"url": "https://a.kr/x"}}

    @pytest.mark.asyncio
    async def test_non_mcp_tool_payload_is_passed_flat(self):
        """내부 도구는 래핑하지 않는다."""
        tool = PlainTool()
        del tool.mcp_input_schema
        tool.mcp_input_schema = _SCHEMA
        llm = FakeLLM(structured_outputs=[_args_out({"url": "https://a.kr/x"})])
        node = _make_node(tool, llm)

        await node(_state())

        assert tool.calls[0] == {"url": "https://a.kr/x"}

    @pytest.mark.asyncio
    async def test_result_body_is_tool_output_not_llm_synthesis(self):
        """②: 산출 본문이 도구 원본이어야 한다 (분석 혼입 방지)."""
        tool = FakeTool(result="원본 페이지 텍스트 A")
        llm = FakeLLM(structured_outputs=[_args_out({"url": "https://a.kr/x"})])
        node = _make_node(tool, llm)

        result = await node(_state())

        assert "원본 페이지 텍스트 A" in _body(result)


class TestCollectCompression:
    @pytest.mark.asyncio
    async def test_short_result_is_not_compressed(self):
        """FR-09: 임계치 이하는 원본 무손실 통과, 압축 LLM 미호출."""
        tool = FakeTool(result="짧음")
        llm = FakeLLM(structured_outputs=[_args_out({"url": "https://a.kr/x"})])
        node = _make_node(tool, llm, CollectPipelinePolicy(compress_threshold=100))

        result = await node(_state())

        assert llm.compress_calls == 0
        assert "짧음" in _body(result)

    @pytest.mark.asyncio
    async def test_long_result_is_compressed_once(self):
        tool = FakeTool(result="가" * 500)
        llm = FakeLLM(
            structured_outputs=[_args_out({"url": "https://a.kr/x"})],
            compress_text="요약본",
        )
        node = _make_node(tool, llm, CollectPipelinePolicy(compress_threshold=100))

        result = await node(_state())

        assert llm.compress_calls == 1
        assert "요약본" in _body(result)

    @pytest.mark.asyncio
    async def test_compression_failure_keeps_original(self):
        """§6.1 #6: 압축 실패는 원본 유지 — 그래프 비중단."""
        tool = FakeTool(result="나" * 500)

        class BoomLLM(FakeLLM):
            async def ainvoke(self, _messages):
                self.compress_calls += 1
                raise RuntimeError("compress down")

        llm = BoomLLM(structured_outputs=[_args_out({"url": "https://a.kr/x"})])
        node = _make_node(tool, llm, CollectPipelinePolicy(compress_threshold=100))

        result = await node(_state())

        assert "나" * 10 in _body(result)


class TestCollectFailureBranches:
    """§6.1 실패 분기 매트릭스 — 어느 분기도 예외를 전파하지 않는다."""

    @pytest.mark.asyncio
    async def test_argument_llm_failure_skips_tool_call(self):
        """#1: 인자 생성 LLM 예외 → 도구 호출 0회."""
        tool = FakeTool()
        llm = FakeLLM(structured_raises=RuntimeError("llm down"))
        node = _make_node(tool, llm)

        result = await node(_state())

        assert tool.calls == []
        assert is_search_result(result["messages"][0])

    @pytest.mark.asyncio
    async def test_not_grounded_skips_tool_call_and_reports_missing(self):
        """#2: grounded=False → 도구 호출 0회, missing 사유가 본문에 포함."""
        tool = FakeTool()
        llm = FakeLLM(structured_outputs=[
            _args_out({}, grounded=False, missing="수집할 URL이 대화에 없습니다"),
        ])
        node = _make_node(tool, llm)

        result = await node(_state())

        assert tool.calls == []
        assert "수집할 URL이 대화에 없습니다" in _body(result)

    @pytest.mark.asyncio
    async def test_placeholder_argument_is_blocked_before_tool_call(self):
        """#3: 플레이스홀더 URL → 도구 호출 0회, 차단 접두어 본문."""
        tool = FakeTool()
        llm = FakeLLM(structured_outputs=[
            _args_out({"url": "https://www.example.com/page"}),
        ])
        node = _make_node(tool, llm)

        result = await node(_state())

        assert tool.calls == []
        assert ToolArgumentPolicy.BLOCKED_PREFIX in _body(result)

    @pytest.mark.asyncio
    async def test_missing_schema_skips_tool_call(self):
        """#4: 입력 스키마 부재 → 추측 인자로 호출하지 않는다."""
        tool = FakeTool(schema={})
        llm = FakeLLM(structured_outputs=[_args_out({"url": "https://a.kr/x"})])
        node = _make_node(tool, llm)

        result = await node(_state())

        assert tool.calls == []
        assert is_search_result(result["messages"][0])

    @pytest.mark.asyncio
    async def test_unparsable_arguments_skip_tool_call(self):
        """구조화 출력이 JSON이 아니면 추측하지 않고 근거 부족으로 처리."""
        tool = FakeTool()
        bad = MagicMock()
        bad.arguments_json = "{not json"
        bad.grounded = True
        bad.missing = ""
        llm = FakeLLM(structured_outputs=[bad])
        node = _make_node(tool, llm)

        result = await node(_state())

        assert tool.calls == []
        assert is_search_result(result["messages"][0])

    @pytest.mark.asyncio
    async def test_tool_exception_does_not_propagate(self):
        """#5: 도구 호출 예외 → 실패 문자열, 예외 전파 없음."""
        tool = FakeTool(raises=RuntimeError("mcp server down"))
        llm = FakeLLM(structured_outputs=[_args_out({"url": "https://a.kr/x"})])
        node = _make_node(tool, llm)

        result = await node(_state())

        assert len(tool.calls) == 1
        assert is_search_result(result["messages"][0])
        assert "실패" in _body(result)


class TestCollectMessageContract:
    """④: 모든 분기가 근거 메시지 규약을 따른다 (FR-08)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tool_factory,outputs",
        [
            (lambda: FakeTool(), [_args_out({"url": "https://a.kr/x"})]),
            (lambda: FakeTool(schema={}), [_args_out({"url": "https://a.kr/x"})]),
            (lambda: FakeTool(), [_args_out({}, grounded=False, missing="없음")]),
            (
                lambda: FakeTool(),
                [_args_out({"url": "https://example.com/x"})],
            ),
            (
                lambda: FakeTool(raises=RuntimeError("boom")),
                [_args_out({"url": "https://a.kr/x"})],
            ),
        ],
    )
    async def test_every_branch_yields_one_search_result_message(
        self, tool_factory, outputs
    ):
        node = _make_node(tool_factory(), FakeLLM(structured_outputs=outputs))

        result = await node(_state())

        messages = result["messages"]
        assert len(messages) == 1
        assert is_search_result(messages[0])
        assert messages[0].name == "scrape_worker"

    @pytest.mark.asyncio
    async def test_returns_last_worker_id_and_step_summary(self):
        tool = FakeTool()
        llm = FakeLLM(structured_outputs=[_args_out({"url": "https://a.kr/x"})])
        node = _make_node(tool, llm)

        result = await node(_state())

        assert result["last_worker_id"] == "scrape_worker"
        assert result["token_usage"] >= 0
        assert "_step_output_summary" in result


class TestCollectPipelinePolicy:
    def test_default_threshold_matches_search_pipeline(self):
        assert CollectPipelinePolicy().compress_threshold == 4000

    def test_custom_threshold(self):
        assert CollectPipelinePolicy(compress_threshold=100).compress_threshold == 100

    def test_invalid_threshold_falls_back_to_default(self):
        assert CollectPipelinePolicy(compress_threshold=0).compress_threshold == 4000
        assert CollectPipelinePolicy(compress_threshold=-5).compress_threshold == 4000

    def test_needs_compression(self):
        policy = CollectPipelinePolicy(compress_threshold=10)
        assert policy.needs_compression("x" * 11) is True
        assert policy.needs_compression("x" * 10) is False

    def test_single_shot_contract_is_one(self):
        """단일샷 계약은 상수다 — 설정으로 바뀌지 않는다."""
        assert CollectPipelinePolicy.TOOL_CALLS_PER_RUN == 1


class TestCollectBodyResolution:
    """Analysis Gap-02: 4갈래 분기를 노드 본문에서 분리한 헬퍼의 계약.

    Design §10.4가 '단계별 헬퍼로 분해'를 지시했는데 노드 본문에 분기가
    인라인으로 남아 40줄 규칙을 넘었다. 분기 결정을 _resolve_body로 추출한다.
    """

    @pytest.mark.asyncio
    async def test_shortage_branch_does_not_invoke_tool(self):
        from src.application.agent_builder.collect_pipeline import (
            _ArgumentPlan,
            _resolve_body,
        )

        tool = FakeTool()
        outcome = await _resolve_body(
            plan=_ArgumentPlan(None, "대상 없음"),
            tool=tool,
            llm=FakeLLM(),
            policy=CollectPipelinePolicy(),
            question="q",
            logger=MagicMock(),
            context_block="",
        )

        assert tool.calls == []
        assert outcome.invoked is False
        assert outcome.blocked_value is None
        assert "대상 없음" in outcome.body

    @pytest.mark.asyncio
    async def test_blocked_branch_does_not_invoke_tool(self):
        from src.application.agent_builder.collect_pipeline import (
            _ArgumentPlan,
            _resolve_body,
        )

        tool = FakeTool()
        outcome = await _resolve_body(
            plan=_ArgumentPlan({"url": "https://example.com/x"}),
            tool=tool,
            llm=FakeLLM(),
            policy=CollectPipelinePolicy(),
            question="q",
            logger=MagicMock(),
            context_block="",
        )

        assert tool.calls == []
        assert outcome.blocked_value == "https://example.com/x"
        assert ToolArgumentPolicy.BLOCKED_PREFIX in outcome.body

    @pytest.mark.asyncio
    async def test_success_branch_invokes_once(self):
        from src.application.agent_builder.collect_pipeline import (
            _ArgumentPlan,
            _resolve_body,
        )

        tool = FakeTool(result="본문")
        outcome = await _resolve_body(
            plan=_ArgumentPlan({"url": "https://a.kr/x"}),
            tool=tool,
            llm=FakeLLM(),
            policy=CollectPipelinePolicy(),
            question="q",
            logger=MagicMock(),
            context_block="",
        )

        assert len(tool.calls) == 1
        assert outcome.invoked is True
        assert outcome.body == "본문"

    @pytest.mark.asyncio
    async def test_tool_failure_branch_reports_without_raising(self):
        from src.application.agent_builder.collect_pipeline import (
            _ArgumentPlan,
            _resolve_body,
        )

        tool = FakeTool(raises=RuntimeError("down"))
        outcome = await _resolve_body(
            plan=_ArgumentPlan({"url": "https://a.kr/x"}),
            tool=tool,
            llm=FakeLLM(),
            policy=CollectPipelinePolicy(),
            question="q",
            logger=MagicMock(),
            context_block="",
        )

        assert outcome.invoked is True
        assert outcome.compressed is False
        assert "실패" in outcome.body


class TestCollectFunctionLength:
    """Analysis Gap-02: CLAUDE.md §3 함수 길이 40줄 규칙.

    측정에서 제외하는 것:
      - docstring / 주석 / 빈 줄
      - **중첩 함수의 본문** — 노드 팩토리는 클로저를 반환하므로 그대로 세면
        내부 노드 함수를 두 번 계산해 팩토리가 항상 위반으로 잡힌다
        (기존 create_search_pipeline_node도 같은 이유로 49가 나온다).
    """

    @staticmethod
    def _code_lines(node, lines) -> int:
        nested = {
            no
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            for no in range(child.lineno, child.end_lineno + 1)
        }
        doc = ast.get_docstring(node)
        doc_span = set()
        if doc:
            first = node.body[0]
            doc_span = set(range(first.lineno, first.end_lineno + 1))
        count = 0
        for no in range(node.lineno, node.end_lineno + 1):
            if no in nested or no in doc_span:
                continue
            text = lines[no - 1].strip()
            if text and not text.startswith("#"):
                count += 1
        return count

    def test_collect_pipeline_functions_are_within_limit(self):
        path = "src/application/agent_builder/collect_pipeline.py"
        source = io.open(path, encoding="utf-8").read()
        lines = source.splitlines()
        over = [
            f"{n.name}={self._code_lines(n, lines)}"
            for n in ast.walk(ast.parse(source))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and self._code_lines(n, lines) > 40
        ]

        assert over == [], f"40줄 초과 함수: {over}"

    def test_measurement_matches_existing_peer_module(self):
        """같은 잣대로 기존 동종 모듈(search_pipeline)도 통과해야 한다.

        새 규칙을 신규 코드에만 엄격히 적용하면 측정이 자의적이라는 뜻이다.
        """
        path = "src/application/agent_builder/search_pipeline.py"
        source = io.open(path, encoding="utf-8").read()
        lines = source.splitlines()
        over = [
            f"{n.name}={self._code_lines(n, lines)}"
            for n in ast.walk(ast.parse(source))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and self._code_lines(n, lines) > 40
        ]

        assert over == [], f"기존 모듈 위반: {over}"
