"""action 노드 단위 테스트.

Design Ref: action-category-compose-node §2.1 / §6.1 / §8.2 (#11~#17)

핵심 계약:
  ① compose(에이전트 모델) 1회 → 초안. 인자 조립(보조 LLM) 1회.
  ② 본문 키는 초안 원문으로 덮어쓴다 — LLM이 무엇을 채웠든 (D-04).
  ③ 게이트 대상이면 도구 0회 + approval_pending(draft == 초안). 아니면 정확히 1회, 재시도 없음.
  ④ 어떤 분기도 예외를 올리지 않고, 초안 규약(is_draft_output) 메시지 1건을 반환한다.
  ⑤ 로그·스텝 요약에 초안·인자 값이 실리지 않는다.
"""
import json
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.action_pipeline import create_action_node
from src.application.agent_builder.search_pipeline import (
    format_search_result,
    is_draft_output,
    split_draft_output,
)
from src.application.agent_run.step_tracking import STEP_OUTPUT_SUMMARY_KEY
from src.domain.approval.policies import ApprovalSignalPolicy
from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy

W = "mail_sender"
TOOL_ID = "mcp:3f2a1b4c-0000-1111-2222-333344445555:send_mail"
DRAFT = "안녕하세요 고객님,\n\n문의하신 건은 처리 완료되었습니다.\n\n감사합니다."
_SCHEMA = {
    "type": "object",
    "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["to", "body"],
}


class FakeTool:
    def __init__(self, result="메일 발송 성공 (id=42)", raises=None, schema=_SCHEMA):
        self.name = "send_mail"
        self.description = "메일을 발송합니다"
        self.mcp_tool_name = "send_mail"
        self.mcp_input_schema = schema
        self.calls: list = []
        self._result = result
        self._raises = raises

    async def ainvoke(self, payload):
        self.calls.append(payload)
        if self._raises is not None:
            raise self._raises
        return self._result


class PlainTool(FakeTool):
    """내부 도구 — MCP 래핑 없음."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.mcp_tool_name = None
        self.args_schema = None


class FakeComposeLLM:
    """에이전트 모델 — ainvoke 1회로 초안을 돌려준다."""

    def __init__(self, draft=DRAFT, raises=None):
        self._draft = draft
        self._raises = raises
        self.calls: list = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        if self._raises is not None:
            raise self._raises
        return AIMessage(content=self._draft)


class FakeStructured:
    def __init__(self, out, raises=None):
        self._out = out
        self._raises = raises

    async def ainvoke(self, _messages):
        if self._raises is not None:
            raise self._raises
        return self._out


class FakePipelineLLM:
    def __init__(self, out=None, raises=None):
        self._out = out
        self._raises = raises
        self.structured_calls = 0

    def with_structured_output(self, _schema):
        self.structured_calls += 1
        return FakeStructured(self._out, self._raises)


def _args_out(arguments: dict, grounded=True, missing=""):
    out = MagicMock()
    out.arguments_json = json.dumps(arguments, ensure_ascii=False)
    out.grounded = grounded
    out.missing = missing
    return out


class FakeLogger:
    def __init__(self):
        self.records: list[tuple[str, str, dict]] = []

    def _rec(self, level):
        def _log(msg, **kw):
            self.records.append((level, msg, kw))
        return _log

    def __getattr__(self, name):
        if name in ("info", "warning", "error", "debug"):
            return self._rec(name)
        raise AttributeError(name)

    def dump(self) -> str:
        return json.dumps(self.records, ensure_ascii=False, default=str)


def _state(extra_messages=()):
    return {
        "messages": [
            HumanMessage(content="이 문의에 회신 메일 보내줘. 수신자는 kim@customer.co.kr"),
            *extra_messages,
        ],
        "token_usage": 0,
    }


def _node(tool=None, compose=None, pipeline=None, gated=False, logger=None, draft_key="body"):
    return create_action_node(
        worker_id=W,
        tool=tool or FakeTool(),
        tool_id=TOOL_ID,
        llm=compose or FakeComposeLLM(),
        pipeline_llm=pipeline or FakePipelineLLM(_args_out({"to": "kim@customer.co.kr", "subject": "회신"})),
        draft_key=draft_key,
        gated=gated,
        logger=logger or FakeLogger(),
        datetime_block="[날짜]\n",
        user_context_block="[사용자]\n",
        worker_context_block="[워커]\n",
    )


# ── #11 즉시 집행 ─────────────────────────────────────────────────


class TestDispatchPath:
    @pytest.mark.asyncio
    async def test_calls_tool_exactly_once_with_draft_in_body(self):
        tool, compose, pipeline = FakeTool(), FakeComposeLLM(), FakePipelineLLM(
            _args_out({"to": "kim@customer.co.kr", "subject": "회신", "body": "LLM이 지어낸 본문"})
        )
        out = await _node(tool, compose, pipeline)(_state())

        assert len(tool.calls) == 1
        assert tool.calls[0] == {"arguments": {"to": "kim@customer.co.kr", "subject": "회신", "body": DRAFT}}
        assert len(compose.calls) == 1
        assert pipeline.structured_calls == 1
        assert "approval_pending" not in out

    @pytest.mark.asyncio
    async def test_emits_single_draft_message(self):
        out = await _node()(_state())
        assert len(out["messages"]) == 1
        msg = out["messages"][0]
        assert is_draft_output(msg)
        assert split_draft_output(msg) == (W, DRAFT, "메일 발송 성공 (id=42)")
        assert out["last_worker_id"] == W
        assert out["last_worker_error"] == ""
        assert out["token_usage"] > 0

    @pytest.mark.asyncio
    async def test_plain_tool_payload_not_wrapped(self):
        tool = PlainTool()
        await _node(tool)(_state())
        assert tool.calls[0] == {"to": "kim@customer.co.kr", "subject": "회신", "body": DRAFT}

    @pytest.mark.asyncio
    async def test_compose_sees_evidence_and_conversation(self):
        """선행 워커 산출은 시스템 프롬프트 근거 블록으로, 대화는 메시지로 간다."""
        compose = FakeComposeLLM()
        evidence = AIMessage(content=format_search_result("searcher", "문의 이력: 배송 지연"), name="searcher")
        await _node(compose=compose)(_state([evidence]))
        messages = compose.calls[0]
        system = messages[0]["content"]
        assert "문의 이력: 배송 지연" in system
        assert "[날짜]" in system and "[사용자]" in system and "[워커]" in system
        assert all(getattr(m, "name", None) != "searcher" for m in messages[1:])
        assert getattr(messages[-1], "type", "") == "human"

    @pytest.mark.asyncio
    async def test_dispatch_failure_is_reported_not_raised(self):
        tool = FakeTool(raises=RuntimeError("smtp down"))
        out = await _node(tool)(_state())
        assert len(tool.calls) == 1
        _, draft, outcome = split_draft_output(out["messages"][0])
        assert draft == DRAFT
        assert "집행 실패" in outcome
        assert out["last_worker_error"]

    @pytest.mark.asyncio
    async def test_long_result_is_truncated(self):
        tool = FakeTool(result="x" * 10000)
        out = await _node(tool)(_state())
        assert len(split_draft_output(out["messages"][0])[2]) < 10000


# ── #12 게이트 대기 ───────────────────────────────────────────────


class TestGatedPath:
    @pytest.mark.asyncio
    async def test_no_tool_call_and_signal_matches_draft(self):
        tool = FakeTool()
        out = await _node(tool, gated=True)(_state())

        assert tool.calls == []
        pending = out["approval_pending"]
        assert pending["tool_id"] == TOOL_ID
        assert pending["draft"] == DRAFT
        assert pending["tool_args"]["body"] == DRAFT
        assert pending["tool_args"]["to"] == "kim@customer.co.kr"
        assert pending["worker_id"] == W
        assert len(pending["tool_call_id"]) == 32 and int(pending["tool_call_id"], 16) >= 0
        assert out["last_worker_error"] == ""

    @pytest.mark.asyncio
    async def test_signal_round_trips_through_policy(self):
        """노드가 만든 dict는 ApprovalSignalPolicy.extract 결과와 같은 키·값이다."""
        out = await _node(gated=True)(_state())
        pending = out["approval_pending"]
        rendered = ApprovalSignalPolicy.render(
            tool_id=pending["tool_id"], tool_args=pending["tool_args"],
            draft=pending["draft"], tool_call_id=pending["tool_call_id"],
        )
        signal = ApprovalSignalPolicy.extract([AIMessage(content=rendered)])
        assert signal.tool_args == pending["tool_args"]
        assert signal.draft == pending["draft"]

    @pytest.mark.asyncio
    async def test_outcome_says_pending(self):
        out = await _node(gated=True)(_state())
        _, draft, outcome = split_draft_output(out["messages"][0])
        assert draft == DRAFT
        assert "승인 대기" in outcome

    @pytest.mark.asyncio
    async def test_fail_closed_when_signal_cannot_be_built(self, monkeypatch):
        """§7: 게이트 대상인데 신호를 못 만들면 도구를 호출하지 않는다."""
        def _boom(**_kw):
            raise RuntimeError("render broke")
        monkeypatch.setattr(ApprovalSignalPolicy, "render", _boom)
        tool = FakeTool()
        out = await _node(tool, gated=True)(_state())
        assert tool.calls == []
        assert "approval_pending" not in out
        assert out["last_worker_error"]


# ── #13~#15 작성·조립 실패 ──────────────────────────────────────


class TestComposeAndAssembleFailures:
    @pytest.mark.asyncio
    async def test_compose_exception_skips_everything(self):
        tool, pipeline = FakeTool(), FakePipelineLLM(_args_out({"to": "a@b.c"}))
        out = await _node(tool, FakeComposeLLM(raises=RuntimeError("llm down")), pipeline)(_state())
        assert tool.calls == [] and pipeline.structured_calls == 0
        _, draft, outcome = split_draft_output(out["messages"][0])
        assert draft == "" and "초안 작성 실패" in outcome
        assert out["last_worker_error"]

    @pytest.mark.asyncio
    async def test_empty_draft_is_failure(self):
        tool = FakeTool()
        out = await _node(tool, FakeComposeLLM(draft="   \n"))(_state())
        assert tool.calls == []
        assert "초안" in split_draft_output(out["messages"][0])[2]
        assert out["last_worker_error"]

    @pytest.mark.asyncio
    async def test_ungrounded_arguments_keep_draft_but_skip_tool(self):
        tool = FakeTool()
        pipeline = FakePipelineLLM(_args_out({}, grounded=False, missing="수신자 주소"))
        out = await _node(tool, pipeline=pipeline)(_state())
        assert tool.calls == []
        _, draft, outcome = split_draft_output(out["messages"][0])
        assert draft == DRAFT
        assert "수신자 주소" in outcome
        assert out["last_worker_error"]

    @pytest.mark.asyncio
    async def test_argument_llm_exception(self):
        tool = FakeTool()
        out = await _node(tool, pipeline=FakePipelineLLM(raises=RuntimeError("x")))(_state())
        assert tool.calls == []
        assert "인자" in split_draft_output(out["messages"][0])[2]

    @pytest.mark.asyncio
    async def test_unparseable_arguments(self):
        bad = MagicMock(); bad.arguments_json = "{not json"; bad.grounded = True; bad.missing = ""
        tool = FakeTool()
        out = await _node(tool, pipeline=FakePipelineLLM(bad))(_state())
        assert tool.calls == []
        assert out["last_worker_error"]

    @pytest.mark.asyncio
    async def test_placeholder_argument_blocked(self):
        """ToolArgumentPolicy는 예약 호스트 URL을 잡는다 — 지어낸 링크가 인자에 섞이면 차단."""
        tool = FakeTool()
        pipeline = FakePipelineLLM(
            _args_out({"to": "kim@customer.co.kr", "link": "https://example.com/track"})
        )
        out = await _node(tool, pipeline=pipeline)(_state())
        assert tool.calls == []
        assert ToolArgumentPolicy.is_blocked_message(split_draft_output(out["messages"][0])[2])
        assert out["last_worker_error"]

    @pytest.mark.asyncio
    async def test_gated_but_ungrounded_does_not_signal(self):
        """인자를 못 만들면 승인 요청도 만들지 않는다 — 빈 수신자를 사람이 승인하게 두지 않는다."""
        pipeline = FakePipelineLLM(_args_out({}, grounded=False, missing="수신자"))
        out = await _node(pipeline=pipeline, gated=True)(_state())
        assert "approval_pending" not in out


# ── ⑤ 관측 ────────────────────────────────────────────────────────


class TestObservability:
    @pytest.mark.asyncio
    async def test_logs_and_summary_contain_no_values(self):
        logger = FakeLogger()
        out = await _node(logger=logger)(_state())
        summary = out[STEP_OUTPUT_SUMMARY_KEY]
        assert "kim@customer.co.kr" not in summary and "고객님" not in summary
        dumped = logger.dump()
        assert "kim@customer.co.kr" not in dumped and "고객님" not in dumped
        assert "body" in summary and "to" in summary
        assert "gated=False" in summary and "invoked=True" in summary

    @pytest.mark.asyncio
    async def test_summary_reports_gate(self):
        out = await _node(gated=True)(_state())
        assert "gated=True" in out[STEP_OUTPUT_SUMMARY_KEY]
        assert "invoked=False" in out[STEP_OUTPUT_SUMMARY_KEY]


# ── GAP-I2 / GAP-I3 (Analysis §5) ─────────────────────────────────


class TestDispatchErrorResponses:
    @pytest.mark.asyncio
    async def test_error_text_response_is_failure(self):
        """§6.1 #8: MCP 어댑터는 도구 오류를 'Error executing tool…' 문자열로 돌려준다 —
        예외가 아니어도 실패로 기록해야 final_answer가 성공으로 보고하지 않는다."""
        tool = FakeTool(result="Error executing tool send_mail: smtp rejected")
        out = await _node(tool)(_state())
        assert len(tool.calls) == 1
        _, draft, outcome = split_draft_output(out["messages"][0])
        assert draft == DRAFT
        assert "smtp rejected" in outcome
        assert out["last_worker_error"]
        assert "ok=False" in out[STEP_OUTPUT_SUMMARY_KEY]

    @pytest.mark.asyncio
    async def test_failure_outcome_is_truncated(self):
        """FR-25: 실패 문구도 상한 절단 — 예외 전문이 final_answer 프롬프트로 전파되지 않는다."""
        tool = FakeTool(raises=RuntimeError("x" * 20000))
        out = await _node(tool)(_state())
        outcome = split_draft_output(out["messages"][0])[2]
        assert len(outcome) <= 4100
        assert out["last_worker_error"]
