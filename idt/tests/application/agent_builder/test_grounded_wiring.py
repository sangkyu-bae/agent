"""근거 재작성 루프 연결 — action 초안 · final_answer.

Design Ref: draft-grounding-check v0.2 §5.2, §5.3, §8.3 (I1–I4).

핵심 계약:
  ① grounded 활성이면 초안·답변이 판정 → 재작성본으로 교체된다.
  ② 비활성이면 기존과 호출 수·프롬프트가 같다 (태그 config 도 붙이지 않는다).
  ③ 루프 안 LLM 호출은 INTERNAL_LLM_TAG 로 채팅 스트림에서 빠진다.
  ④ final_answer 는 근거(워커 산출)가 없으면 판정하지 않는다.
"""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.action_pipeline import create_action_node
from src.application.agent_builder.search_pipeline import format_search_result, split_draft_output
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.application.hallucination.grounded_generation import GroundedGenerator
from src.domain.hallucination.grounding import (
    INTERNAL_LLM_TAG,
    GroundingJudgePort,
    GroundingVerdict,
    UnsupportedClaim,
)
from src.infrastructure.agent_builder.tool_factory import ToolFactory

W = "inquiry_replier"
TOOL_ID = "mcp:3f2a1b4c-0000-1111-2222-333344445555:submit_reply"
BAD = "안녕하세요. 대표번호 1877-9900 으로 문의하세요. 감사합니다."
GOOD = "안녕하세요. 고객센터로 문의해 주세요. 감사합니다."
EVIDENCE = format_search_result("inquiry_reader", "[문의 63116] 추가대출 가능 여부 문의")
_SCHEMA = {
    "type": "object",
    "properties": {"inquiry_id": {"type": "string"}, "reply_content": {"type": "string"}},
    "required": ["inquiry_id", "reply_content"],
}


def _verdict(*spans):
    return GroundingVerdict(unsupported_claims=tuple(
        UnsupportedClaim(span=s, reason="근거 없음", severity="high") for s in spans
    ))


class FakeJudge(GroundingJudgePort):
    def __init__(self, verdicts=()):
        self.verdicts = list(verdicts)
        self.calls: list[dict] = []

    async def judge(self, **kwargs):
        self.calls.append(kwargs)
        return self.verdicts.pop(0) if self.verdicts else _verdict()


class RecordingLLM:
    """ainvoke 호출마다 (messages, config) 를 기록하고 순서대로 응답한다."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls: list[tuple[list, dict | None]] = []

    async def ainvoke(self, messages, config=None):
        self.calls.append((messages, config))
        return AIMessage(content=self.outputs.pop(0))


class PlainLLM:
    """config 인자를 받지 않는 기존 형태 — 비활성 경로가 config 를 넘기면 TypeError."""

    def __init__(self, output):
        self.output = output
        self.calls: list = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=self.output)


class FakeTool:
    name = "submit_reply"
    description = "문의에 답변을 등록합니다"
    mcp_tool_name = "submit_reply"
    mcp_input_schema = _SCHEMA

    async def ainvoke(self, payload):  # pragma: no cover — 게이트 경로라 호출되지 않음
        raise AssertionError("gated 노드는 도구를 호출하지 않는다")


class FakeStructured:
    async def ainvoke(self, _messages):
        out = MagicMock()
        out.arguments_json = '{"inquiry_id": "63116"}'
        out.grounded, out.missing = True, ""
        return out


class FakePipelineLLM:
    def with_structured_output(self, _schema):
        return FakeStructured()


def _grounded(judge, enabled=True):
    return GroundedGenerator(judge, MagicMock(), enabled=enabled, corpus_max_chars=24000)


def _system_of(messages) -> str:
    return messages[0]["content"]


# ── action 초안 ──────────────────────────────────────────────────


def _action_node(llm, grounded=None):
    return create_action_node(
        worker_id=W, tool=FakeTool(), tool_id=TOOL_ID, llm=llm,
        pipeline_llm=FakePipelineLLM(), draft_key="reply_content", gated=True,
        logger=MagicMock(), worker_context_block="[워커]\n친절하되 단호한 말투\n",
        grounded=grounded, grounding_max_retries=2, request_id="req-1",
    )


def _action_state():
    return {
        "messages": [
            HumanMessage(content="63116 글을 읽고 답변까지 등록해줘"),
            AIMessage(content=EVIDENCE, name="inquiry_reader"),
        ],
        "token_usage": 0,
    }


class TestActionDraftGrounding:
    @pytest.mark.asyncio
    async def test_재작성본이_승인_초안이_된다(self):
        """I1"""
        judge = FakeJudge([_verdict("1877-9900"), _verdict()])
        llm = RecordingLLM([BAD, GOOD])
        out = await _action_node(llm, _grounded(judge))(_action_state())

        assert out["approval_pending"]["draft"] == GOOD
        assert out["approval_pending"]["tool_args"]["reply_content"] == GOOD
        assert split_draft_output(out["messages"][0])[1] == GOOD
        # 재작성 사유는 system 끝에 실린다
        assert "[근거 검토 결과]" in _system_of(llm.calls[1][0])
        assert "[근거 검토 결과]" not in _system_of(llm.calls[0][0])
        # 루프 안 호출은 모두 내부 태그
        assert all(cfg == {"tags": [INTERNAL_LLM_TAG]} for _, cfg in llm.calls)

    @pytest.mark.asyncio
    async def test_판정기에_질문과_근거_코퍼스를_넘긴다(self):
        judge = FakeJudge([_verdict()])
        await _action_node(RecordingLLM([GOOD]), _grounded(judge))(_action_state())

        call = judge.calls[0]
        assert call["question"] == "63116 글을 읽고 답변까지 등록해줘"
        assert "[문의 63116] 추가대출 가능 여부 문의" in call["sources"]
        assert "친절하되 단호한 말투" in call["sources"]
        assert call["generation"] == GOOD and call["request_id"] == "req-1"

    @pytest.mark.asyncio
    async def test_제거_후_빈_초안이면_작성_실패(self):
        """D-07 — 초안이 비면 승인 신호를 만들지 않는다."""
        judge = FakeJudge([_verdict(BAD)] * 3)
        out = await _action_node(RecordingLLM([BAD, BAD, BAD]), _grounded(judge))(_action_state())

        assert "approval_pending" not in out
        assert out["last_worker_error"].startswith("초안 작성 실패")

    @pytest.mark.asyncio
    async def test_첫_작성_실패는_기존_실패_경로(self):
        class Broken:
            async def ainvoke(self, messages, config=None):
                raise RuntimeError("llm down")

        judge = FakeJudge()
        out = await _action_node(Broken(), _grounded(judge))(_action_state())
        assert "approval_pending" not in out
        assert out["last_worker_error"].startswith("초안 작성 실패")
        assert judge.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("grounded", [None, "disabled"])
    async def test_비활성이면_기존과_동일(self, grounded):
        """I2 — 호출 1회, config 없음, 판정 0회."""
        judge = FakeJudge()
        gen = _grounded(judge, enabled=False) if grounded else None
        llm = PlainLLM(BAD)
        out = await _action_node(llm, gen)(_action_state())

        assert len(llm.calls) == 1
        assert out["approval_pending"]["draft"] == BAD
        assert judge.calls == []


# ── final_answer ─────────────────────────────────────────────────


def _final_node(llm, grounded=None):
    compiler = WorkflowCompiler(
        tool_factory=MagicMock(spec=ToolFactory), llm_factory=MagicMock(), logger=MagicMock(),
        grounded_generator=grounded, answer_grounding_max_retries=1,
    )
    return compiler._create_final_answer_node(llm, "당신은 문의 응대 에이전트입니다.")


def _final_state(with_evidence=True):
    messages = [HumanMessage(content="63116 문의 요약해줘")]
    if with_evidence:
        messages.append(AIMessage(content=EVIDENCE, name="inquiry_reader"))
    return {"messages": messages, "token_usage": 0}


class TestFinalAnswerGrounding:
    @pytest.mark.asyncio
    async def test_재작성본을_AIMessage_1건으로_반환(self):
        """I3"""
        judge = FakeJudge([_verdict("1877-9900"), _verdict()])
        llm = RecordingLLM([BAD, GOOD])
        out = await _final_node(llm, _grounded(judge))(_final_state())

        assert len(out["messages"]) == 1
        assert isinstance(out["messages"][0], AIMessage)
        assert out["messages"][0].content == GOOD
        assert all(cfg == {"tags": [INTERNAL_LLM_TAG]} for _, cfg in llm.calls)
        assert "[근거 검토 결과]" in _system_of(llm.calls[1][0])
        assert "[문의 63116]" in judge.calls[0]["sources"]
        assert judge.calls[0]["question"] == "63116 문의 요약해줘"

    @pytest.mark.asyncio
    async def test_상한_1회_초과면_문장_제거(self):
        judge = FakeJudge([_verdict("1877-9900")] * 2)
        llm = RecordingLLM([BAD, BAD])
        out = await _final_node(llm, _grounded(judge))(_final_state())

        assert len(llm.calls) == 2
        assert out["messages"][0].content == "안녕하세요. 감사합니다."

    @pytest.mark.asyncio
    async def test_근거_없으면_판정하지_않는다(self):
        """I4 — 태그도 붙이지 않아 기존 스트리밍 유지."""
        judge = FakeJudge()
        llm = PlainLLM(BAD)
        out = await _final_node(llm, _grounded(judge))(_final_state(with_evidence=False))

        assert judge.calls == [] and len(llm.calls) == 1
        assert out["messages"][0].content == BAD

    @pytest.mark.asyncio
    async def test_차트만_있으면_판정하지_않는다(self):
        """Analysis G-3 — D-09 는 워커 산출 기준."""
        judge = FakeJudge()
        llm = PlainLLM(BAD)
        state = {**_final_state(with_evidence=False), "charts": [{"type": "bar", "title": "t"}]}
        await _final_node(llm, _grounded(judge))(state)
        assert judge.calls == [] and len(llm.calls) == 1

    @pytest.mark.asyncio
    async def test_코퍼스는_최신_워커_산출_우선(self):
        """Analysis G-4 / D-10 — 상한 절단 시 최신 산출이 남는다."""
        judge = FakeJudge([_verdict()])
        state = _final_state()
        state["messages"].append(AIMessage(content="[최신 조회] 답변완료 상태", name="status_reader"))
        await _final_node(RecordingLLM([GOOD]), _grounded(judge))(state)
        sources = judge.calls[0]["sources"]
        assert sources.index("[최신 조회]") < sources.index("[문의 63116]")

    @pytest.mark.asyncio
    async def test_교체된_답변도_응답_메타데이터를_보존한다(self):
        """Analysis G-5 — usage·response_metadata 유실 방지."""
        class MetaLLM(RecordingLLM):
            async def ainvoke(self, messages, config=None):
                msg = await super().ainvoke(messages, config)
                return AIMessage(content=msg.content, response_metadata={"model_name": "m"})

        judge = FakeJudge([_verdict("1877-9900")] * 2)
        out = await _final_node(MetaLLM([BAD, BAD]), _grounded(judge))(_final_state())
        msg = out["messages"][0]
        assert msg.content == "안녕하세요. 감사합니다."
        assert msg.response_metadata == {"model_name": "m"}

    @pytest.mark.asyncio
    async def test_미주입이면_기존과_동일(self):
        llm = PlainLLM(BAD)
        out = await _final_node(llm)(_final_state())
        assert len(llm.calls) == 1 and out["messages"][0].content == BAD
