"""PiiMaskingMiddleware 테스트 — Design §4.3 (FR-01, FR-02, FR-03, FR-09).

그래프 테스트는 create_agent를 실제로 컴파일·실행한다. fake 스트림만으로는
집계 경로를 덮지 못한다는 선례(prompt-guard `charts: None`)를 따른다.
"""

from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware
from langchain.agents.middleware.types import ExtendedModelResponse, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel
from src.application.approval.gate_middleware import ApprovalGateMiddleware
from src.application.middleware.middleware_builder import MiddlewareBuilder
from src.application.pii_masking.middleware import PiiMaskingMiddleware
from src.application.pii_masking.stream_restorer import PlaceholderStreamRestorer
from src.domain.pii_masking.policies import PII_PLACEHOLDER_NOTICE

from tests.application.pii_masking._scripted_model import ScriptedChatModel, sent_text
from tests.application.pii_masking._support import make_masker, make_service

PHONE = "010-1234-5678"
EMAIL = "hong@example.com"
TOOL_PHONE = "010-9999-8888"


def _call(args: dict, call_id: str = "c1") -> AIMessage:
    return AIMessage(
        content="", tool_calls=[{"name": "send", "args": args, "id": call_id}]
    )


def _agent(model, middleware, tool_log):
    @tool
    def send(to: str) -> str:
        """메시지를 보낸다."""
        tool_log.append(to)
        return f"sent to {to}, 문의 {TOOL_PHONE}"

    return create_agent(
        model=model,
        tools=[send],
        system_prompt=f"담당자 {PHONE}",
        middleware=middleware,
        name="worker",
    )


async def _run(agent, text: str):
    tokens, final = [], None
    async for ev in agent.astream_events(
        {"messages": [HumanMessage(content=text)]}, version="v2"
    ):
        if ev["event"] == "on_chat_model_stream":
            tokens.append((ev["run_id"], ev["data"]["chunk"].content))
        if ev["event"] == "on_chain_end" and ev["name"] == "worker":
            final = ev["data"]["output"]
    return tokens, final


class TestGraph:
    async def test_external_request_masked_tool_and_state_original(self):
        masker = make_masker()
        scope = masker.new_scope()
        model = ScriptedChatModel(
            script=[
                _call({"to": "[EMAIL_1]"}),
                AIMessage(content="[EMAIL_1] 로 전송했습니다"),
            ]
        )
        tool_log: list = []
        agent = _agent(model, [PiiMaskingMiddleware(masker, scope)], tool_log)
        _, final = await _run(agent, f"{EMAIL} 로 보내")

        sent = sent_text(model)
        for value in (PHONE, EMAIL, TOOL_PHONE):
            assert value not in sent
        assert "담당자 [PHONE_1]" in sent
        assert tool_log == [EMAIL]
        state = [m.content for m in final["messages"]]
        assert state[0] == f"{EMAIL} 로 보내"
        assert state[-1] == f"{EMAIL} 로 전송했습니다"
        assert final["messages"][1].tool_calls[0]["args"] == {"to": EMAIL}

    async def test_stream_tokens_restored_by_restorer(self):
        masker = make_masker()
        scope = masker.new_scope()
        model = ScriptedChatModel(script=[AIMessage(content="[PHONE_1] 로 연락하세요")])
        agent = _agent(model, [PiiMaskingMiddleware(masker, scope)], [])
        tokens, _ = await _run(agent, f"{PHONE} 알려줘")

        assert any("[PH" in chunk for _, chunk in tokens)  # 원복기 없이는 조각 노출
        restorer = PlaceholderStreamRestorer(make_service(), scope)
        shown = [restorer.feed(str(run_id), chunk) for run_id, chunk in tokens]
        shown += [restorer.flush(str(run_id)) for run_id in {r for r, _ in tokens}]
        assert "".join(shown) == f"{PHONE} 로 연락하세요"
        assert not any("[" in piece for piece in shown)

    async def test_orphan_placeholder_in_tool_args_blocks_tool(self):
        masker = make_masker()
        model = ScriptedChatModel(
            script=[
                _call({"to": "[EMAIL_9]"}),
                AIMessage(content="확인이 필요합니다"),
            ]
        )
        tool_log: list = []
        agent = _agent(
            model, [PiiMaskingMiddleware(masker, masker.new_scope())], tool_log
        )
        _, final = await _run(agent, "보내줘")

        assert tool_log == []
        notice = final["messages"][2]
        assert isinstance(notice, ToolMessage)
        assert notice.tool_call_id == "c1"
        assert notice.status == "error"
        assert "[EMAIL_9]" not in notice.content

    async def test_approval_gate_sees_original_args(self):
        # FR-03 체인 순서: PII 미들웨어가 바깥이라 게이트는 원복된 인자를 본다.
        masker = make_masker()
        model = ScriptedChatModel(
            script=[
                _call({"to": "[EMAIL_1]"}),
                AIMessage(content="승인 대기"),
            ]
        )
        tool_log: list = []
        gate = ApprovalGateMiddleware(tool_id="send", worker_id="worker")
        middleware = [PiiMaskingMiddleware(masker, masker.new_scope()), gate]
        _, final = await _run(_agent(model, middleware, tool_log), f"{EMAIL} 로 보내")

        marker = final["messages"][2]
        assert tool_log == []
        assert EMAIL in marker.content
        assert EMAIL not in sent_text(model)

    async def test_retry_inside_chain_resends_masked_request(self):
        masker = make_masker()
        model = ScriptedChatModel(
            script=[AIMessage(content="ok")],
            fail_first=1,
        )
        middleware = [
            PiiMaskingMiddleware(masker, masker.new_scope()),
            ModelRetryMiddleware(max_retries=1, initial_delay=0.0),
        ]
        await _run(_agent(model, middleware, []), f"{PHONE} 확인")
        assert len(model.seen) == 2
        assert PHONE not in sent_text(model)

    async def test_shadow_mode_sends_original_and_counts(self):
        masker = make_masker("shadow")
        scope = masker.new_scope()
        model = ScriptedChatModel(script=[AIMessage(content="ok")])
        await _run(_agent(model, [PiiMaskingMiddleware(masker, scope)], []), PHONE)
        assert PHONE in sent_text(model)
        assert scope.vault.counts()


@dataclass
class _Request:
    messages: list
    system_message: SystemMessage | None = None

    def override(self, **kwargs):
        return _Request(**{**self.__dict__, **kwargs})


class TestResultShapes:
    async def test_handler_returning_ai_message_restored(self):
        masker = make_masker()
        mw = PiiMaskingMiddleware(masker, masker.new_scope())

        async def handler(request):
            return AIMessage(content="[PHONE_1]")

        out = await mw.awrap_model_call(
            _Request([HumanMessage(content=PHONE)]), handler
        )
        assert out.content == PHONE

    async def test_model_response_structured_output_restored(self):
        class Answer(BaseModel):
            text: str

        masker = make_masker()
        mw = PiiMaskingMiddleware(masker, masker.new_scope())

        async def handler(request):
            return ModelResponse(
                result=[AIMessage(content="[PHONE_1]")],
                structured_response=Answer(text="[PHONE_1] 입니다"),
            )

        out = await mw.awrap_model_call(
            _Request([HumanMessage(content=PHONE)]), handler
        )
        assert out.result[0].content == PHONE
        assert out.structured_response == Answer(text=f"{PHONE} 입니다")

    async def test_extended_model_response_restored(self):
        masker = make_masker()
        mw = PiiMaskingMiddleware(masker, masker.new_scope())

        async def handler(request):
            inner = ModelResponse(result=[AIMessage(content="[PHONE_1]")])
            return ExtendedModelResponse(model_response=inner, command=None)

        out = await mw.awrap_model_call(
            _Request([HumanMessage(content=PHONE)]), handler
        )
        assert out.model_response.result[0].content == PHONE

    def test_sync_wrap_model_call_masks_system_message(self):
        masker = make_masker()
        mw = PiiMaskingMiddleware(masker, masker.new_scope())
        seen = []

        def handler(request):
            seen.append(request)
            return AIMessage(content="ok")

        mw.wrap_model_call(
            _Request([HumanMessage(content="hi")], SystemMessage(content=PHONE)),
            handler,
        )
        assert seen[0].system_message.content == (
            "[PHONE_1]\n\n" + PII_PLACEHOLDER_NOTICE
        )

    async def test_notice_added_as_system_when_only_messages_masked(self):
        # Check G-13: system 이 없는 워커도 안내를 받는다.
        masker = make_masker()
        mw = PiiMaskingMiddleware(masker, masker.new_scope())
        seen = []

        async def handler(request):
            seen.append(request)
            return AIMessage(content="ok")

        await mw.awrap_model_call(_Request([HumanMessage(content=PHONE)]), handler)
        assert seen[0].system_message.content == PII_PLACEHOLDER_NOTICE
        assert seen[0].messages[0].content == "[PHONE_1]"

    async def test_no_notice_without_pii(self):
        masker = make_masker()
        mw = PiiMaskingMiddleware(masker, masker.new_scope())
        seen = []

        async def handler(request):
            seen.append(request)
            return AIMessage(content="ok")

        await mw.awrap_model_call(_Request([HumanMessage(content="hi")]), handler)
        assert seen[0].system_message is None


class TestBuilder:
    def test_build_pii_masking_returns_new_instance_each_call(self):
        masker = make_masker()
        scope = masker.new_scope()
        first = MiddlewareBuilder.build_pii_masking(masker=masker, scope=scope)
        second = MiddlewareBuilder.build_pii_masking(masker=masker, scope=scope)
        assert isinstance(first, PiiMaskingMiddleware)
        assert first is not second
        assert first.scope is second.scope is scope
