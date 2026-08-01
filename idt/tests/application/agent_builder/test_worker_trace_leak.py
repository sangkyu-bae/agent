"""워커 트레이스 유출 회귀 테스트 (TC-01~06).

worker-toolmessage-leak-fix Design §5.1 — react agent 내부 트레이스
(tool_calls AIMessage·ToolMessage)가 supervisor state로 유출되면
final_answer_node에서 고아 tool 메시지로 OpenAI 400을 유발한다.

- D1: _wrap_worker는 최종 AIMessage(name=worker_id) 1건만 반환
- D2: final_answer_node LLM 입력에 tool 역할 메시지 제외
- D3: token_delta는 최종 답변 기준 (입력 히스토리 미합산)
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.infrastructure.agent_builder.tool_factory import ToolFactory


def _make_compiler() -> WorkflowCompiler:
    tool_factory = MagicMock(spec=ToolFactory)
    llm_factory = MagicMock()
    logger = MagicMock()
    return WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=logger,
    )


def _react_agent_returning(messages: list) -> AsyncMock:
    agent = AsyncMock()
    agent.ainvoke.return_value = {"messages": messages}
    return agent


def _trace_messages(final_content: str = "위키 문서에 따르면 X입니다.") -> list:
    """도구를 1회 호출한 react agent의 전형적 결과 메시지."""
    return [
        HumanMessage(content="X가 뭐야?"),
        AIMessage(
            content="",
            name="worker_0",
            tool_calls=[{"name": "wiki_read", "args": {"id": "doc-1"}, "id": "call_1"}],
        ),
        ToolMessage(content="X 문서 본문", tool_call_id="call_1", name="wiki_read"),
        AIMessage(content=final_content, name="worker_0"),
    ]


def _role_of(msg) -> str:
    if isinstance(msg, dict):
        return msg.get("role", "")
    return getattr(msg, "type", "")


class TestWrapWorkerNoTraceLeak:
    @pytest.mark.asyncio
    async def test_tc01_tool_trace_not_leaked(self):
        """TC-01: 도구 호출 트레이스 → 최종 AIMessage(name=worker_id) 1건만 반환."""
        compiler = _make_compiler()
        agent = _react_agent_returning(_trace_messages("위키 문서에 따르면 X입니다."))

        wrapped = compiler._wrap_worker("worker_0", agent)
        result = await wrapped({
            "messages": [HumanMessage(content="X가 뭐야?")],
            "token_usage": 0,
        })

        out = result["messages"]
        assert len(out) == 1, f"워커 산출물은 1건이어야 함, got {len(out)}"
        msg = out[0]
        assert getattr(msg, "type", "") == "ai"
        assert msg.name == "worker_0"
        assert msg.content == "위키 문서에 따르면 X입니다."
        assert not getattr(msg, "tool_calls", []), "tool_calls가 유출되면 안 됨"

    @pytest.mark.asyncio
    async def test_tc02_direct_answer_same_contract(self):
        """TC-02: 도구 호출 없는 직답도 동일 규약 1건 반환."""
        compiler = _make_compiler()
        agent = _react_agent_returning([
            HumanMessage(content="질문"),
            AIMessage(content="직답입니다.", name="worker_0"),
        ])

        wrapped = compiler._wrap_worker("worker_0", agent)
        result = await wrapped({
            "messages": [HumanMessage(content="질문")],
            "token_usage": 0,
        })

        out = result["messages"]
        assert len(out) == 1
        assert out[0].name == "worker_0"
        assert out[0].content == "직답입니다."

    @pytest.mark.asyncio
    async def test_tc03_token_delta_from_final_answer_only(self):
        """TC-03: token 델타는 최종 답변 기준 — 입력 히스토리·중간 트레이스 미합산."""
        compiler = _make_compiler()
        final = "위키 문서에 따르면 X입니다."
        agent = _react_agent_returning(_trace_messages(final))

        wrapped = compiler._wrap_worker("worker_0", agent)
        result = await wrapped({
            "messages": [HumanMessage(content="X가 뭐야?")],
            "token_usage": 100,
        })

        assert result["token_usage"] == 100 + len(final) // 4

    @pytest.mark.asyncio
    async def test_tc04_empty_result_graceful(self):
        """TC-04: react agent 결과 messages 빈 리스트 → 빈 content AIMessage, 예외 없음."""
        compiler = _make_compiler()
        agent = _react_agent_returning([])

        wrapped = compiler._wrap_worker("worker_0", agent)
        result = await wrapped({
            "messages": [HumanMessage(content="질문")],
            "token_usage": 0,
        })

        out = result["messages"]
        assert len(out) == 1
        assert out[0].name == "worker_0"
        assert out[0].content == ""
        assert result["last_worker_id"] == "worker_0"


class TestFinalAnswerToolDefense:
    def _make_node(self, mock_llm):
        return _make_compiler()._create_final_answer_node(
            mock_llm, "당신은 AI 에이전트입니다."
        )

    def _mock_llm(self) -> AsyncMock:
        llm = AsyncMock()
        llm.ainvoke.return_value = AIMessage(content="최종 답변")
        return llm

    @pytest.mark.asyncio
    async def test_tc05_orphan_toolmessage_excluded(self):
        """TC-05: state에 고아 ToolMessage → LLM 입력에 tool 역할 부재."""
        mock_llm = self._mock_llm()
        node = self._make_node(mock_llm)

        state = {
            "messages": [
                HumanMessage(content="질문"),
                ToolMessage(content="고아 도구 결과", tool_call_id="call_x", name="t"),
                AIMessage(content="[w 검색결과]\n자료", name="w"),
            ],
            "token_usage": 0,
        }
        await node(state)

        sent = mock_llm.ainvoke.call_args[0][0]
        assert all(_role_of(m) != "tool" for m in sent), (
            "tool 역할 메시지가 LLM 입력에 포함되면 OpenAI 400"
        )

    @pytest.mark.asyncio
    async def test_tc06_dict_tool_role_excluded(self):
        """TC-06: dict 형태 role=tool 혼입도 동일하게 제외."""
        mock_llm = self._mock_llm()
        node = self._make_node(mock_llm)

        state = {
            "messages": [
                HumanMessage(content="질문"),
                {"role": "tool", "content": "dict 도구 결과", "tool_call_id": "call_y"},
                AIMessage(content="[w 검색결과]\n자료", name="w"),
            ],
            "token_usage": 0,
        }
        await node(state)

        sent = mock_llm.ainvoke.call_args[0][0]
        assert all(_role_of(m) != "tool" for m in sent)
