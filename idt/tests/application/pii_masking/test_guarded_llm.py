"""GuardedLlm 프록시 단위 테스트 — Design §4.4 (FR-05)."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel
from src.application.pii_masking.guarded_llm import GuardedLlm
from src.domain.pii_masking.policies import PII_PLACEHOLDER_NOTICE

from tests.application.pii_masking._support import make_masker

PHONE = "010-1234-5678"
OTHER = "010-9999-8888"


class _Recorder(Runnable):
    """내부 모델 자리의 명시적 fake. 받은 입력·config를 기록한다."""

    def __init__(self, reply, model_name: str = "fake-model") -> None:
        self.reply = reply
        self.model_name = model_name
        self.inputs: list = []
        self.configs: list = []
        self.structured_schema = None
        self.bound_tools = None

    def invoke(self, input, config=None, **kwargs):
        self.inputs.append(input)
        self.configs.append(config)
        return self.reply(input) if callable(self.reply) else self.reply

    async def ainvoke(self, input, config=None, **kwargs):
        return self.invoke(input, config, **kwargs)

    def with_structured_output(self, schema, **kwargs):
        child = _Recorder(self.reply, self.model_name)
        child.structured_schema = schema
        self.child = child
        return child

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = tools
        return self


def _texts(messages) -> list[str]:
    """안내(Check G-13)를 떼어 낸 본문. 안내 자체는 TestNotice 가 검사한다."""
    return [
        m.content.removesuffix("\n\n" + PII_PLACEHOLDER_NOTICE)
        for m in messages
        if m.content != PII_PLACEHOLDER_NOTICE
    ]


class TestNotice:
    async def test_notice_appended_to_existing_system(self):
        inner = _Recorder(AIMessage(content="ok"))
        await GuardedLlm(inner, make_masker()).ainvoke(
            [SystemMessage(content="규칙"), HumanMessage(content=PHONE)]
        )
        sent = inner.inputs[0]
        assert len(sent) == 2
        assert sent[0].content == "규칙\n\n" + PII_PLACEHOLDER_NOTICE

    async def test_notice_inserted_as_first_system_when_absent(self):
        inner = _Recorder(AIMessage(content="ok"))
        await GuardedLlm(inner, make_masker()).ainvoke(f"{PHONE}로 보내")
        sent = inner.inputs[0]
        assert isinstance(sent[0], SystemMessage)
        assert sent[0].content == PII_PLACEHOLDER_NOTICE
        assert sent[1].content == "[PHONE_1]로 보내"

    async def test_no_notice_without_pii(self):
        inner = _Recorder(AIMessage(content="ok"))
        await GuardedLlm(inner, make_masker()).ainvoke("금리 알려줘")
        assert [m.content for m in inner.inputs[0]] == ["금리 알려줘"]


class TestAinvoke:
    async def test_ainvoke_inner_receives_masked_and_output_restored(self):
        inner = _Recorder(AIMessage(content="[PHONE_1] 로 보냄"))
        guarded = GuardedLlm(inner, make_masker())
        out = await guarded.ainvoke(
            [SystemMessage(content=f"담당 {PHONE}"), HumanMessage(content=PHONE)]
        )
        assert _texts(inner.inputs[0]) == ["담당 [PHONE_1]", "[PHONE_1]"]
        assert out.content == f"{PHONE} 로 보냄"

    async def test_ainvoke_string_input_normalized_to_message(self):
        inner = _Recorder(AIMessage(content="ok"))
        await GuardedLlm(inner, make_masker()).ainvoke(f"{PHONE}로 보내")
        assert _texts(inner.inputs[0]) == ["[PHONE_1]로 보내"]

    async def test_ainvoke_prompt_pipe_masks_prompt_value(self):
        inner = _Recorder(AIMessage(content="ok"))
        prompt = ChatPromptTemplate.from_messages([("human", "질문: {q}")])
        chain = prompt | GuardedLlm(inner, make_masker())
        await chain.ainvoke({"q": PHONE})
        assert _texts(inner.inputs[0]) == ["질문: [PHONE_1]"]

    async def test_ainvoke_config_passed_through(self):
        inner = _Recorder(AIMessage(content="ok"))
        config = {"tags": ["grounding_internal"]}
        await GuardedLlm(inner, make_masker()).ainvoke("hi", config)
        assert inner.configs[0] == config

    async def test_ainvoke_without_scope_each_call_independent(self):
        inner = _Recorder(AIMessage(content="ok"))
        guarded = GuardedLlm(inner, make_masker())
        await guarded.ainvoke(PHONE)
        await guarded.ainvoke(OTHER)
        assert _texts(inner.inputs[1]) == ["[PHONE_1]"]

    async def test_ainvoke_with_scope_shares_numbering(self):
        masker = make_masker()
        scope = masker.new_scope()
        inner = _Recorder(AIMessage(content="ok"))
        guarded = GuardedLlm(inner, masker, scope)
        await guarded.ainvoke(PHONE)
        await guarded.ainvoke(OTHER)
        assert _texts(inner.inputs[1]) == ["[PHONE_2]"]

    async def test_ainvoke_shadow_inner_receives_original(self):
        inner = _Recorder(AIMessage(content="ok"))
        await GuardedLlm(inner, make_masker("shadow")).ainvoke(PHONE)
        assert _texts(inner.inputs[0]) == [PHONE]

    async def test_ainvoke_unsupported_input_raises(self):
        guarded = GuardedLlm(_Recorder(AIMessage(content="ok")), make_masker())
        with pytest.raises(TypeError):
            await guarded.ainvoke(12345)


class TestInvoke:
    def test_invoke_sync_masks_and_restores(self):
        inner = _Recorder(AIMessage(content="[PHONE_1]"))
        out = GuardedLlm(inner, make_masker()).invoke(PHONE)
        assert _texts(inner.inputs[0]) == ["[PHONE_1]"]
        assert out.content == PHONE


class TestStructuredOutput:
    async def test_with_structured_output_restores_pydantic(self):
        class Decision(BaseModel):
            next: str
            reason: str

        inner = _Recorder(lambda _: Decision(next="w", reason="[PHONE_1] 확인"))
        structured = GuardedLlm(inner, make_masker()).with_structured_output(Decision)
        assert isinstance(structured, GuardedLlm)
        out = await structured.ainvoke(PHONE)
        assert inner.child.structured_schema is Decision
        assert _texts(inner.child.inputs[0]) == ["[PHONE_1]"]
        assert out == Decision(next="w", reason=f"{PHONE} 확인")

    async def test_with_structured_output_keeps_scope(self):
        masker = make_masker()
        scope = masker.new_scope()
        guarded = GuardedLlm(_Recorder(AIMessage(content="ok")), masker, scope)
        assert guarded.with_structured_output(dict).scope is scope


class TestBindAndDelegate:
    def test_bind_tools_returns_guarded(self):
        inner = _Recorder(AIMessage(content="ok"))
        bound = GuardedLlm(inner, make_masker()).bind_tools(["t"])
        assert isinstance(bound, GuardedLlm)
        assert inner.bound_tools == ["t"]

    def test_attribute_access_delegates_to_inner(self):
        guarded = GuardedLlm(_Recorder(AIMessage(content="ok")), make_masker())
        assert guarded.model_name == "fake-model"

    def test_inner_exposes_wrapped_model(self):
        inner = _Recorder(AIMessage(content="ok"))
        assert GuardedLlm(inner, make_masker()).inner is inner
