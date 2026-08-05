"""builtin-middleware D9: model_call_limit × 워커 그래프 시나리오.

run_limit 도달 시 exit_behavior="end"로 워커가 정상 종료(예외 없음)하고,
마지막 산출물이 AIMessage로 수렴해 _wrap_worker 규약(마지막 메시지 재포장)과
호환됨을 실 create_agent 그래프로 검증한다.

supervisor 수렴: run_limit로 조기 종료된 워커도 _wrap_worker를 거치면
AIMessage(name) 1건 규약을 지키고, 그 state로 route_to_worker_or_final이
final_answer로 수렴함을 단언한다 (Gap G2).
"""
from unittest.mock import MagicMock

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from src.application.agent_builder.supervisor_nodes import route_to_worker_or_final
from src.application.agent_builder.workflow_compiler import WorkflowCompiler


@tool
def echo_tool(text: str) -> str:
    """입력을 그대로 반환."""
    return f"echo: {text}"


class ToolBindableFakeModel(GenericFakeChatModel):
    """GenericFakeChatModel은 bind_tools 미구현 — 테스트용 no-op 바인딩."""

    def bind_tools(self, tools, **kwargs):
        return self


def _tool_calling_model(calls: int) -> ToolBindableFakeModel:
    """매 호출마다 tool_calls를 반환해 무한 루프를 유도하는 fake 모델."""
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "echo_tool", "args": {"text": f"t{i}"}, "id": f"c{i}"}
            ],
        )
        for i in range(calls)
    ]
    return ToolBindableFakeModel(messages=iter(messages))


@pytest.mark.asyncio
async def test_run_limit_도달시_정상_종료():
    model = _tool_calling_model(calls=10)
    agent = create_agent(
        model=model,
        tools=[echo_tool],
        middleware=[ModelCallLimitMiddleware(run_limit=2, exit_behavior="end")],
    )
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "반복해"}]}
    )
    messages = result.get("messages", [])
    assert messages, "run_limit 종료 후에도 messages가 있어야 한다"
    assert isinstance(messages[-1], AIMessage)


def _limited_wrapped_worker(worker_id: str = "worker_0"):
    """run_limit=2로 조기 종료되는 실 create_agent를 _wrap_worker로 감싼 노드."""
    agent = create_agent(
        model=_tool_calling_model(calls=10),
        tools=[echo_tool],
        middleware=[ModelCallLimitMiddleware(run_limit=2, exit_behavior="end")],
    )
    compiler = WorkflowCompiler(
        tool_factory=MagicMock(), llm_factory=MagicMock(), logger=MagicMock(),
    )
    return compiler._wrap_worker(worker_id, agent)


@pytest.mark.asyncio
async def test_run_limit_종료_산출물이_워커_규약_유지():
    """조기 종료 결과도 AIMessage(name=worker_id) 1건 — supervisor 계약 호환."""
    wrapped = _limited_wrapped_worker()
    result = await wrapped(
        {"messages": [HumanMessage(content="반복해")], "token_usage": 0}
    )
    out = result["messages"]
    assert len(out) == 1
    assert isinstance(out[0], AIMessage)
    assert out[0].name == "worker_0"
    assert not getattr(out[0], "tool_calls", []), "tool_calls 유출 금지"
    assert result["last_worker_id"] == "worker_0"


@pytest.mark.asyncio
async def test_run_limit_종료후_라우팅이_final_answer로_수렴():
    """run_limit 종료 워커의 state(last_worker_id)로 FINISH 시 final_answer 경유 —
    supervisor 루프가 재진입 없이 종료로 수렴한다."""
    wrapped = _limited_wrapped_worker()
    result = await wrapped(
        {"messages": [HumanMessage(content="반복해")], "token_usage": 0}
    )
    state = {
        "next_worker": "__end__",
        "last_worker_id": result["last_worker_id"],
    }
    assert route_to_worker_or_final(state) == "final_answer"


@pytest.mark.asyncio
async def test_run_limit_미도달이면_영향_없음():
    model = ToolBindableFakeModel(messages=iter([AIMessage(content="완료")]))
    agent = create_agent(
        model=model,
        tools=[echo_tool],
        middleware=[ModelCallLimitMiddleware(run_limit=5, exit_behavior="end")],
    )
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "안녕"}]}
    )
    assert result["messages"][-1].content == "완료"
