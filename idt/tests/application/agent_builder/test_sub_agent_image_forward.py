"""서브에이전트 이미지 전달/치환 — chat-image-attachment Design FR-07 / D-03 / §8.2 #17.

같은 에이전트의 워커는 supervisor 와 같은 LLM 이므로 모델이 달라지는 지점은
서브에이전트뿐이다. 서브 입력은 텍스트 블록으로 재조립되므로 이미지 전달 여부를
`_wrap_sub_agent` 가 명시적으로 결정한다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.llm.interfaces import LLMFactoryInterface

_IMG_PARENT = {"type": "image_url", "image_url": {"url": "data:image/png;base64,PPPP"}}
_IMG_SUB = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "SSSS"}}


def _compiler(builder=None) -> WorkflowCompiler:
    tool_factory = MagicMock(); tool_factory.create = MagicMock(return_value=MagicMock())
    llm_factory = MagicMock(spec=LLMFactoryInterface); llm_factory.create.return_value = MagicMock()
    return WorkflowCompiler(
        tool_factory=tool_factory, llm_factory=llm_factory, logger=MagicMock(),
        agent_repository=AsyncMock(), image_block_builder=builder, image_detail="high",
    )


def _sub_graph() -> AsyncMock:
    g = AsyncMock()
    g.ainvoke.return_value = {"messages": [AIMessage(content="서브 답")], "token_usage": 1}
    return g


def _state(*, with_image: bool) -> dict:
    content = (
        [{"type": "text", "text": "표의 3분기 값은?"}, _IMG_PARENT] if with_image
        else "표의 3분기 값은?"
    )
    attachments = (
        [{"type": "image", "file_path": "/tmp/a.png", "mime": "image/png", "file_name": "a.png"}]
        if with_image else []
    )
    return {
        "messages": [HumanMessage(content=content), AIMessage(content="w1 결과", name="w1")],
        "worker_task": "표 값을 읽어줘",
        "attachments": attachments,
        "token_usage": 0, "token_limit": 8000, "max_iterations": 20,
    }


def _builder() -> MagicMock:
    b = MagicMock()
    b.build_from_path.return_value = _IMG_SUB
    return b


def _sent_messages(graph: AsyncMock) -> list[dict]:
    return graph.ainvoke.call_args.args[0]["messages"]


class TestForwardWhenSubSupportsVision:
    @pytest.mark.asyncio
    async def test_image_blocks_rebuilt_for_sub_provider_and_appended(self) -> None:
        builder = _builder()
        compiler = _compiler(builder)
        graph = _sub_graph()
        node = compiler._wrap_sub_agent(
            "sub_w", graph, supports_vision=True, provider="anthropic",
        )
        await node(_state(with_image=True))
        sent = _sent_messages(graph)
        last = sent[-1]
        assert last["role"] == "user"
        assert isinstance(last["content"], list)
        assert last["content"][0]["type"] == "text"  # 기존 텍스트 블록 유지
        assert last["content"][-1] == _IMG_SUB     # 서브 provider 포맷으로 재생성
        assert builder.build_from_path.call_args.args[0] == "anthropic"
        assert builder.build_from_path.call_args.kwargs["path"] == "/tmp/a.png"
        # 앞 블록들은 그대로 문자열
        assert all(isinstance(m["content"], str) for m in sent[:-1])

    @pytest.mark.asyncio
    async def test_no_image_in_turn_leaves_input_untouched(self) -> None:
        builder = _builder()
        compiler = _compiler(builder)
        graph = _sub_graph()
        node = compiler._wrap_sub_agent("sub_w", graph, supports_vision=True, provider="openai")
        await node(_state(with_image=False))
        assert all(isinstance(m["content"], str) for m in _sent_messages(graph))
        builder.build_from_path.assert_not_called()


class TestMarkerWhenSubLacksVision:
    @pytest.mark.asyncio
    async def test_marker_appended_instead_of_image(self) -> None:
        compiler = _compiler(_builder())
        graph = _sub_graph()
        node = compiler._wrap_sub_agent("sub_w", graph, supports_vision=False, provider="openai")
        await node(_state(with_image=True))
        last = _sent_messages(graph)[-1]
        assert isinstance(last["content"], str)
        assert "[이미지 첨부: a.png" in last["content"]
        assert "이미지를 볼 수 없" in last["content"]
        assert "PPPP" not in last["content"]

    @pytest.mark.asyncio
    async def test_no_builder_is_treated_as_unsupported(self) -> None:
        compiler = _compiler(None)
        graph = _sub_graph()
        node = compiler._wrap_sub_agent("sub_w", graph, supports_vision=True, provider="openai")
        await node(_state(with_image=True))
        last = _sent_messages(graph)[-1]
        assert isinstance(last["content"], str) and "이미지를 볼 수 없" in last["content"]

    @pytest.mark.asyncio
    async def test_build_failure_falls_back_to_marker(self) -> None:
        builder = _builder()
        builder.build_from_path.side_effect = OSError("gone")
        compiler = _compiler(builder)
        graph = _sub_graph()
        node = compiler._wrap_sub_agent("sub_w", graph, supports_vision=True, provider="openai")
        await node(_state(with_image=True))
        last = _sent_messages(graph)[-1]
        assert isinstance(last["content"], str) and "이미지를 볼 수 없" in last["content"]


class TestLegacyCallSignature:
    @pytest.mark.asyncio
    async def test_default_kwargs_keep_text_only_behaviour(self) -> None:
        compiler = _compiler(_builder())
        graph = _sub_graph()
        node = compiler._wrap_sub_agent("sub_w", graph)  # 기존 호출 시그니처
        await node(_state(with_image=True))
        last = _sent_messages(graph)[-1]
        assert isinstance(last["content"], str)
