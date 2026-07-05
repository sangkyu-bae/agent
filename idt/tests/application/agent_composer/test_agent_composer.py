"""AgentComposer 단위 테스트 — Mock LLM structured output."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_composer.composer import (
    AgentComposer,
    _CapabilityOutput,
    _ComposeOutput,
    _WorkerOutput,
)
from src.application.agent_composer.schemas import ComposeCurrentConfig
from src.domain.agent_composer.schemas import CandidateTool


def _make_output() -> _ComposeOutput:
    return _ComposeOutput(
        capabilities=[
            _CapabilityOutput(
                capability="웹 검색",
                matched_tool_ids=["tavily_search"],
                reason="Tavily로 커버 가능",
            ),
        ],
        workers=[
            _WorkerOutput(
                tool_id="tavily_search",
                worker_id="search_worker",
                description="웹 검색 담당",
                sort_order=0,
            ),
        ],
        flow_hint="search_worker 단독 실행",
        system_prompt="당신은 검색 에이전트입니다.",
        agent_name="검색 도우미",
        notes="",
    )


def _candidates() -> list[CandidateTool]:
    return [
        CandidateTool(
            tool_id="tavily_search",
            name="Tavily 웹 검색",
            description="웹 검색 도구",
            source="internal",
        ),
        CandidateTool(
            tool_id="mcp:srv-1:fetch_page",
            name="fetch_page",
            description="웹 페이지 수집",
            source="mcp",
            mcp_server_id="srv-1",
        ),
    ]


def _make_composer(max_candidates: int = 100):
    mock_llm = MagicMock()
    mock_llm.with_structured_output = MagicMock(return_value=mock_llm)
    mock_llm.ainvoke = AsyncMock(return_value=_make_output())
    logger = MagicMock()
    composer = AgentComposer(
        llm=mock_llm, logger=logger, max_candidates=max_candidates
    )
    return composer, mock_llm, logger


class TestAgentComposer:
    @pytest.mark.asyncio
    async def test_compose_returns_output(self):
        composer, _, _ = _make_composer()
        result = await composer.compose("검색 에이전트 만들어줘", _candidates(), "req-1")
        assert isinstance(result, _ComposeOutput)
        assert result.workers[0].tool_id == "tavily_search"

    @pytest.mark.asyncio
    async def test_compose_injects_candidates_into_system_prompt(self):
        composer, mock_llm, _ = _make_composer()
        await composer.compose("검색 에이전트", _candidates(), "req-1")
        messages = mock_llm.ainvoke.call_args[0][0]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "tavily_search" in system_msg["content"]
        assert "mcp:srv-1:fetch_page" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_compose_truncates_candidates_over_limit_with_warning(self):
        composer, mock_llm, logger = _make_composer(max_candidates=1)
        await composer.compose("검색 에이전트", _candidates(), "req-1")
        messages = mock_llm.ainvoke.call_args[0][0]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "tavily_search" in system_msg["content"]
        assert "mcp:srv-1:fetch_page" not in system_msg["content"]
        logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_compose_raises_and_logs_on_llm_error(self):
        composer, mock_llm, logger = _make_composer()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))
        with pytest.raises(RuntimeError, match="LLM down"):
            await composer.compose("쿼리", _candidates(), "req-1")
        logger.error.assert_called_once()


class TestAgentComposerCurrentConfig:
    """fix-agent-composer B4/B5: 현재 설정 블록 주입 + history 메시지 삽입."""

    def _current_config(self) -> ComposeCurrentConfig:
        return ComposeCurrentConfig(
            name="재무 리포터",
            system_prompt="당신은 재무 데이터 에이전트입니다.",
            tool_ids=["excel_export", "tavily_search"],
            llm_model_id="model-1",
            temperature=0.7,
        )

    @pytest.mark.asyncio
    async def test_current_config_block_injected(self):
        """B4: current_config가 있으면 설정 블록+증분 수정 규칙이 프롬프트에 포함."""
        composer, mock_llm, _ = _make_composer()
        await composer.compose(
            "tavily 도구 추가해줘",
            _candidates(),
            "req-1",
            current_config=self._current_config(),
        )
        messages = mock_llm.ainvoke.call_args[0][0]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "[현재 에이전트 설정]" in system_msg["content"]
        assert "[증분 수정 규칙]" in system_msg["content"]
        assert "재무 리포터" in system_msg["content"]
        assert "excel_export" in system_msg["content"]
        assert "당신은 재무 데이터 에이전트입니다." in system_msg["content"]

    @pytest.mark.asyncio
    async def test_without_current_config_no_block(self):
        """B4: current_config 없으면 블록 미포함 (기존 동작 유지)."""
        composer, mock_llm, _ = _make_composer()
        await composer.compose("검색 에이전트", _candidates(), "req-1")
        messages = mock_llm.ainvoke.call_args[0][0]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "[현재 에이전트 설정]" not in system_msg["content"]
        assert "[증분 수정 규칙]" not in system_msg["content"]

    @pytest.mark.asyncio
    async def test_history_inserted_between_system_and_user(self):
        """B5: history가 system과 최종 user 사이에 순서대로 삽입."""
        composer, mock_llm, _ = _make_composer()
        history = [
            {"role": "user", "content": "재무 에이전트 만들어줘"},
            {"role": "assistant", "content": "초안: 재무 리포터 / 도구: excel_export"},
        ]
        await composer.compose(
            "tavily 도구 추가해줘", _candidates(), "req-1", history=history
        )
        messages = mock_llm.ainvoke.call_args[0][0]
        assert messages[0]["role"] == "system"
        assert messages[1] == history[0]
        assert messages[2] == history[1]
        assert messages[-1] == {"role": "user", "content": "tavily 도구 추가해줘"}


class TestAgentComposerToolInstructions:
    """compose-tool-instructions FR-01/FR-02: 도구별 지침 생성."""

    def test_worker_output_has_instruction_field_with_default(self):
        w = _WorkerOutput(
            tool_id="tavily_search",
            worker_id="search_worker",
            description="웹 검색 담당",
            sort_order=0,
        )
        assert w.instruction == ""

    def test_system_prompt_rule_requires_tool_instruction_section(self):
        """FR-02: 프롬프트 규칙에 [도구 지침] 섹션과 instruction 작성 지시 포함."""
        assert "[도구 지침]" in AgentComposer._SYSTEM_PROMPT
        assert "instruction" in AgentComposer._SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_compose_preserves_worker_instruction(self):
        composer, mock_llm, _ = _make_composer()
        output = _make_output()
        output.workers[0].instruction = "최신 정보 질문에만 사용."
        mock_llm.ainvoke = AsyncMock(return_value=output)
        result = await composer.compose("검색 에이전트", _candidates(), "req-1")
        assert result.workers[0].instruction == "최신 정보 질문에만 사용."


class TestAgentComposerTracing:
    """compose-langsmith-tracing: LangSmith run_name/tags/metadata + tracer 주입."""

    @pytest.mark.asyncio
    async def test_config_has_run_name_tags_metadata(self, monkeypatch):
        monkeypatch.setattr(
            "src.application.agent_composer.composer.make_composer_tracer",
            lambda tags=None: None,
        )
        composer, mock_llm, _ = _make_composer()
        await composer.compose("검색 에이전트 만들어줘", _candidates(), "req-1")
        config = mock_llm.ainvoke.call_args.kwargs["config"]
        assert config["run_name"].startswith("compose:")
        assert "agent-composer" in config["tags"]
        assert config["metadata"]["request_id"] == "req-1"

    @pytest.mark.asyncio
    async def test_run_name_uses_current_config_name(self, monkeypatch):
        """수정 요청이면 기존 에이전트명을 run_name에 사용 — 이름으로 추적 가능."""
        monkeypatch.setattr(
            "src.application.agent_composer.composer.make_composer_tracer",
            lambda tags=None: None,
        )
        composer, mock_llm, _ = _make_composer()
        current = ComposeCurrentConfig(
            name="재무 리포터",
            system_prompt="p",
            tool_ids=["excel_export"],
            llm_model_id="model-1",
            temperature=0.7,
        )
        await composer.compose(
            "도구 추가", _candidates(), "req-1", current_config=current
        )
        config = mock_llm.ainvoke.call_args.kwargs["config"]
        assert config["run_name"] == "compose:재무 리포터"

    @pytest.mark.asyncio
    async def test_tracer_injected_into_callbacks(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(
            "src.application.agent_composer.composer.make_composer_tracer",
            lambda tags=None: sentinel,
        )
        composer, mock_llm, _ = _make_composer()
        await composer.compose("검색 에이전트", _candidates(), "req-1")
        config = mock_llm.ainvoke.call_args.kwargs["config"]
        assert config["callbacks"] == [sentinel]

    @pytest.mark.asyncio
    async def test_no_callbacks_when_tracer_unavailable(self, monkeypatch):
        """API 키 없음 등으로 tracer가 None이면 callbacks 미설정 (본 흐름 무영향)."""
        monkeypatch.setattr(
            "src.application.agent_composer.composer.make_composer_tracer",
            lambda tags=None: None,
        )
        composer, mock_llm, _ = _make_composer()
        await composer.compose("검색 에이전트", _candidates(), "req-1")
        config = mock_llm.ainvoke.call_args.kwargs["config"]
        assert "callbacks" not in config


