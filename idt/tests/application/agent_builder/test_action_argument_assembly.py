"""action 인자 조립 — 본문 제외·파싱 실패 재시도.

Design Ref: approval-gate-run-termination Analysis G1 (Act-2).
실측(런 469872a7): 인자 조립 LLM 이 "본문은 비워라" 지시를 무시하고 수천 자
본문을 arguments_json 에 넣다가 파싱 실패 → 승인 건 없이 요청이 사라졌다.
"""
import json
from unittest.mock import MagicMock

import pytest

from tests.application.agent_builder.test_action_pipeline import (
    DRAFT,
    FakeLogger,
    FakeTool,
    _args_out,
    _node,
    _state,
)


class _SequenceStructured:
    def __init__(self, parent):
        self._parent = parent

    async def ainvoke(self, messages):
        self._parent.prompts.append(messages)
        return self._parent.outputs.pop(0)


class SequencePipelineLLM:
    """호출마다 준비된 출력을 차례로 돌려주고 프롬프트를 기록한다."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts: list = []

    def with_structured_output(self, _schema):
        return _SequenceStructured(self)


def _bad():
    out = MagicMock()
    out.arguments_json = '{"to": "kim@customer.co.kr", "body": "잘린 본문'
    out.grounded = True
    out.missing = ""
    return out


def _user_content(pipeline) -> str:
    return pipeline.prompts[0][1]["content"]


class TestDraftExcludedFromArgumentPrompt:
    @pytest.mark.asyncio
    async def test_스키마에서_본문_키를_뺀다(self):
        pipeline = SequencePipelineLLM([_args_out({"to": "kim@customer.co.kr"})])
        await _node(pipeline=pipeline)(_state())
        content = _user_content(pipeline)
        schema_text = content.split("[입력 스키마]\n", 1)[1].split("\n\n", 1)[0]
        schema = json.loads(schema_text)
        assert "body" not in schema["properties"]
        assert "body" not in schema.get("required", [])
        assert "to" in schema["properties"]

    @pytest.mark.asyncio
    async def test_초안_원문을_프롬프트에_싣지_않는다(self):
        pipeline = SequencePipelineLLM([_args_out({"to": "kim@customer.co.kr"})])
        await _node(pipeline=pipeline)(_state())
        assert DRAFT not in _user_content(pipeline)

    @pytest.mark.asyncio
    async def test_본문은_초안으로_채워진다(self):
        tool = FakeTool()
        pipeline = SequencePipelineLLM([_args_out({"to": "kim@customer.co.kr", "body": "LLM 이 쓴 값"})])
        await _node(tool=tool, pipeline=pipeline)(_state())
        sent = tool.calls[0]
        body = sent.get("arguments", sent).get("body") if isinstance(sent, dict) else None
        assert body == DRAFT


class TestRetryOnParseFailure:
    @pytest.mark.asyncio
    async def test_파싱_실패면_한_번_재시도해서_성공한다(self):
        tool = FakeTool()
        logger = FakeLogger()
        pipeline = SequencePipelineLLM([_bad(), _args_out({"to": "kim@customer.co.kr"})])
        out = await _node(tool=tool, pipeline=pipeline, logger=logger)(_state())
        assert len(pipeline.prompts) == 2
        assert len(tool.calls) == 1
        assert not out["last_worker_error"]
        assert any(msg == "action_node argument parse retry" for _, msg, _ in logger.records)

    @pytest.mark.asyncio
    async def test_재시도도_실패하면_기존대로_실패(self):
        tool = FakeTool()
        pipeline = SequencePipelineLLM([_bad(), _bad()])
        out = await _node(tool=tool, pipeline=pipeline)(_state())
        assert len(pipeline.prompts) == 2
        assert tool.calls == []
        assert out["last_worker_error"]

    @pytest.mark.asyncio
    async def test_성공하면_재시도하지_않는다(self):
        pipeline = SequencePipelineLLM([_args_out({"to": "kim@customer.co.kr"})])
        await _node(pipeline=pipeline)(_state())
        assert len(pipeline.prompts) == 1
