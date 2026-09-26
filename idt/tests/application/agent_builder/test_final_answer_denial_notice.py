"""final_answer 노드의 워커 능력 주장 주의 블록 테스트.

Design Ref: worker-capability-denial-guard §6.2 Q1 (module-6 실런 확정)
Plan SC: FR-10

실런(런 a217f45e): 되물음은 발동했지만 supervisor가 FINISH를 유지했고,
final_answer가 워커의 "본문은 어떤 도구로도 조회 불가" 주장을 그대로 종합했다.
supervisor의 안내 블록은 final_answer에 닿지 않으므로, 이번 턴 워커 산출을
같은 패턴으로 결정적으로 재판정해 조건부 주의 블록을 싣는다 (LLM 호출 0회 추가).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.infrastructure.agent_builder.tool_factory import ToolFactory

PATTERNS = ("어떤 도구로도",)
_DENIAL = "목록 48건.\n본문은 어떤 도구로도 조회할 수 없도록 제한되어 있습니다."
_OK = "목록 48건입니다."


def _node(mock_llm, patterns=PATTERNS):
    compiler = WorkflowCompiler(
        tool_factory=MagicMock(spec=ToolFactory), llm_factory=MagicMock(),
        logger=MagicMock(), capability_denial_patterns=patterns,
    )
    return compiler._create_final_answer_node(mock_llm, "당신은 AI 에이전트입니다.")


def _llm() -> AsyncMock:
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(content="답")
    return llm


def _system_prompt(llm) -> str:
    return llm.ainvoke.call_args[0][0][0]["content"]


class TestDenialNotice:

    @pytest.mark.asyncio
    async def test_notice_when_current_turn_worker_denies(self):
        llm = _llm()
        await _node(llm)({
            "messages": [
                HumanMessage(content="본문 읽을 수 있나요?"),
                AIMessage(content=_DENIAL, name="lister"),
            ],
            "token_usage": 0,
        })
        prompt = _system_prompt(llm)
        assert "[워커 능력 주장 주의]" in prompt
        assert "그대로 옮기지" in prompt

    @pytest.mark.asyncio
    async def test_no_notice_when_worker_output_is_normal(self):
        llm = _llm()
        await _node(llm)({
            "messages": [HumanMessage(content="q"), AIMessage(content=_OK, name="lister")],
            "token_usage": 0,
        })
        assert "[워커 능력 주장 주의]" not in _system_prompt(llm)

    @pytest.mark.asyncio
    async def test_no_notice_when_patterns_not_injected(self):
        """미주입 경로 무회귀 — 기존 final_answer 프롬프트와 동일."""
        llm = _llm()
        await _node(llm, patterns=None)({
            "messages": [HumanMessage(content="q"), AIMessage(content=_DENIAL, name="lister")],
            "token_usage": 0,
        })
        assert "[워커 능력 주장 주의]" not in _system_prompt(llm)

    @pytest.mark.asyncio
    async def test_prior_turn_worker_output_does_not_trigger(self):
        """이번 턴 산출만 판정 — 이전 턴 워커 메시지는 재주입·맥락일 뿐이다."""
        llm = _llm()
        await _node(llm)({
            "messages": [
                HumanMessage(content="첫 질문"),
                AIMessage(content=_DENIAL, name="lister"),
                AIMessage(content="이전 턴 답"),
                HumanMessage(content="두 번째 질문"),
                AIMessage(content=_OK, name="lister"),
            ],
            "token_usage": 0,
        })
        assert "[워커 능력 주장 주의]" not in _system_prompt(llm)

    @pytest.mark.asyncio
    async def test_notice_does_not_enumerate_tool_names(self):
        """그래프 계약 ② — 도구·워커 이름을 나열하지 않는다."""
        llm = _llm()
        await _node(llm)({
            "messages": [HumanMessage(content="q"), AIMessage(content=_DENIAL, name="lister")],
            "token_usage": 0,
        })
        prompt = _system_prompt(llm)
        start = prompt.index("[워커 능력 주장 주의]")
        assert "get_inquiry" not in prompt[start:]
        assert "lister" not in prompt[start:]


class TestNoticeGroundedInWorkerList:
    """Act-1 Gap-04: 주의 블록의 판단 근거는 에이전트 지침이 아니라 등록 워커 목록.

    실런 295d2915: 에이전트 지침 자체가 결함 문구("원문 확인 불가")를 담고 있어
    지침을 가리키는 주의 블록이 이길 수 없었다. 발동 시에만 supervisor와 같은
    워커 설명 목록을 조건부로 싣는다.
    """

    _WORKERS = "- lister: 문의 목록 조회\n- reader: 문의 한 건의 본문 조회"

    def _node_with_workers(self, llm):
        compiler = WorkflowCompiler(
            tool_factory=MagicMock(spec=ToolFactory), llm_factory=MagicMock(),
            logger=MagicMock(), capability_denial_patterns=PATTERNS,
        )
        return compiler._create_final_answer_node(
            llm, "당신은 AI 에이전트입니다.", worker_descriptions=self._WORKERS,
        )

    @pytest.mark.asyncio
    async def test_notice_includes_registered_workers_when_denial(self):
        llm = _llm()
        await self._node_with_workers(llm)({
            "messages": [HumanMessage(content="q"), AIMessage(content=_DENIAL, name="lister")],
            "token_usage": 0,
        })
        prompt = _system_prompt(llm)
        start = prompt.index("[워커 능력 주장 주의]")
        assert "등록된 워커" in prompt[start:]
        assert "reader: 문의 한 건의 본문 조회" in prompt[start:]
        assert "에이전트 지침에 있는" not in prompt[start:]

    @pytest.mark.asyncio
    async def test_workers_not_listed_without_denial(self):
        """발동하지 않으면 워커 목록도 싣지 않는다 — 기존 프롬프트 동일."""
        llm = _llm()
        await self._node_with_workers(llm)({
            "messages": [HumanMessage(content="q"), AIMessage(content=_OK, name="lister")],
            "token_usage": 0,
        })
        assert "등록된 워커" not in _system_prompt(llm)
