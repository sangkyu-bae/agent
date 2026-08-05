"""builtin-middleware D0: create_react_agent → create_agent 전환 동등성 게이트.

모킹 없이 실제 create_agent 그래프로 다음 현행 계약을 특성(characterization)
테스트로 고정한다:
- 시그니처: system_prompt / name / middleware 파라미터 존재 (설계 전제)
- astream_events(version="v2")가 on_chat_model_stream 토큰 이벤트를 발화
- 최종 산출물이 AIMessage로 수렴 (워커 래퍼 _wrap_worker의 입력 전제)
"""
import inspect

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


def test_create_agent_signature_contract():
    """설계 전제 파라미터가 설치 버전에 존재한다 (D0 스모크)."""
    params = set(inspect.signature(create_agent).parameters)
    assert {"model", "tools", "system_prompt", "middleware", "name"} <= params


def test_middleware_classes_importable():
    """1차 미들웨어 4종 import 성공 (S1)."""
    from langchain.agents.middleware import (  # noqa: F401
        ModelCallLimitMiddleware,
        ModelFallbackMiddleware,
        ModelRetryMiddleware,
        ToolRetryMiddleware,
    )


@pytest.mark.asyncio
async def test_astream_events_emits_token_stream():
    """General Chat 계약: on_chat_model_stream 이벤트 + 최종 AIMessage."""
    model = GenericFakeChatModel(messages=iter([AIMessage(content="안녕하세요")]))
    agent = create_agent(model=model, tools=[], system_prompt="테스트")

    stream_events = []
    final_state = None
    async for ev in agent.astream_events(
        {"messages": [{"role": "user", "content": "인사해줘"}]}, version="v2"
    ):
        if ev.get("event") == "on_chat_model_stream":
            stream_events.append(ev)
        if ev.get("event") == "on_chain_end" and ev.get("name") == "LangGraph":
            final_state = ev.get("data", {}).get("output")

    assert stream_events, "on_chat_model_stream 이벤트가 발화되어야 한다"
    assert final_state is not None
    messages = final_state.get("messages", [])
    assert messages and isinstance(messages[-1], AIMessage)
    assert "안녕" in messages[-1].content


@pytest.mark.asyncio
async def test_ainvoke_returns_messages_dict():
    """워커 래퍼(_wrap_worker) 입력 전제: ainvoke 결과 dict에 messages 존재."""
    model = GenericFakeChatModel(messages=iter([AIMessage(content="완료")]))
    agent = create_agent(model=model, tools=[], name="worker_0")

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "작업"}]}
    )
    assert "messages" in result
    assert isinstance(result["messages"][-1], AIMessage)
