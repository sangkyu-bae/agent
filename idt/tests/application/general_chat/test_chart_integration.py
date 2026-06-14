"""GeneralChatUseCase chart-builder 연동 테스트.

_maybe_build_charts 판단 분기 + stream/execute charts 주입 검증.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage

from src.application.general_chat.use_case import GeneralChatUseCase
from src.domain.general_chat.schemas import GeneralChatRequest
from src.domain.general_chat.value_objects import ChatEventType
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.domain.visualization.chart_policy import ChartStylePolicy
from src.domain.visualization.chart_schemas import (
    ChartConfig,
    ChartData,
    ChartDataset,
    ChartType,
)
from src.domain.visualization.policies import VisualizationRoutingPolicy


def _llm_model() -> LlmModel:
    return LlmModel(
        id="t", provider="openai", model_name="gpt-4o", display_name="x",
        description=None, api_key_env="OPENAI_API_KEY", max_tokens=1000,
        is_active=True, is_default=True,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


def _sample_config() -> ChartConfig:
    return ChartConfig(
        type=ChartType.BAR,
        data=ChartData(
            labels=["a", "b"],
            datasets=[ChartDataset(label="s", data=[1.0, 2.0])],
        ),
        options={"responsive": True},
    )


class _FakeBuilder:
    def __init__(self, result: list[ChartConfig] | Exception) -> None:
        self._result = result
        self.called = False
        self.last_context = None

    async def build(self, question, analysis_text, context=""):
        self.called = True
        self.last_context = context
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _FakeClassifier:
    def __init__(self, decision: str) -> None:
        self._decision = decision
        self.called = False

    async def classify(self, question, analysis_text):
        self.called = True
        return self._decision


def _make_uc(
    answer: str,
    chart_builder=None,
    classifier=None,
) -> GeneralChatUseCase:
    mock_tool_builder = AsyncMock()
    mock_tool_builder.build.return_value = []

    mock_msg_repo = AsyncMock()
    mock_msg_repo.find_by_session.return_value = []
    mock_msg_repo.save.return_value = MagicMock()

    mock_policy = MagicMock()
    mock_policy.needs_summarization = MagicMock(return_value=False)

    mock_llm_factory = MagicMock(spec=LLMFactoryInterface)
    mock_llm_factory.create.return_value = MagicMock()

    mock_agent = AsyncMock()

    async def _fake_astream_events(input_dict, version=None):
        result = {"messages": [AIMessage(content=answer)]}
        yield {"event": "on_chain_end", "data": {"output": result}, "name": "agent"}

    mock_agent.astream_events = _fake_astream_events

    uc = GeneralChatUseCase(
        chat_tool_builder=mock_tool_builder,
        message_repo=mock_msg_repo,
        summary_repo=AsyncMock(),
        summarizer=AsyncMock(),
        summarization_policy=mock_policy,
        logger=MagicMock(),
        llm_factory=mock_llm_factory,
        llm_model=_llm_model(),
        viz_policy=VisualizationRoutingPolicy(),
        viz_classifier=classifier,
        chart_builder=chart_builder,
    )
    uc._create_agent = MagicMock(return_value=mock_agent)
    return uc


async def _charts_from_stream(uc, message: str) -> list:
    req = GeneralChatRequest(user_id="u1", session_id="s1", message=message)
    async for ev in uc.stream(req, request_id="r1"):
        if ev.event_type == ChatEventType.ANSWER_COMPLETED:
            return ev.payload.get("charts", "MISSING")
    return "NO_ANSWER_EVENT"


class TestMaybeBuildCharts:
    async def test_explicit_keyword_builds_chart_without_classifier(self) -> None:
        builder = _FakeBuilder([_sample_config()])
        classifier = _FakeClassifier("text")
        uc = _make_uc("매출 100 130", chart_builder=builder, classifier=classifier)
        charts = await _charts_from_stream(uc, "매출 그래프 그려줘")
        assert len(charts) == 1
        assert builder.called is True
        assert classifier.called is False  # 명시 키워드 → classifier 미호출

    async def test_non_numeric_answer_returns_empty(self) -> None:
        builder = _FakeBuilder([_sample_config()])
        uc = _make_uc("간단한 설명입니다", chart_builder=builder)
        charts = await _charts_from_stream(uc, "설명해줘")
        assert charts == []
        assert builder.called is False

    async def test_ambiguous_classifier_visualize_builds(self) -> None:
        builder = _FakeBuilder([_sample_config()])
        classifier = _FakeClassifier("visualize")
        # 키워드 없음 + 수치 다수 → None → classifier
        uc = _make_uc(
            "2023 100, 2024 130, 2025 160, 12% 증가",
            chart_builder=builder, classifier=classifier,
        )
        charts = await _charts_from_stream(uc, "추세 알려줘")
        assert classifier.called is True
        assert len(charts) == 1

    async def test_ambiguous_classifier_text_no_chart(self) -> None:
        builder = _FakeBuilder([_sample_config()])
        classifier = _FakeClassifier("text")
        uc = _make_uc(
            "2023 100, 2024 130, 2025 160, 12% 증가",
            chart_builder=builder, classifier=classifier,
        )
        charts = await _charts_from_stream(uc, "추세 알려줘")
        assert classifier.called is True
        assert charts == []
        assert builder.called is False

    async def test_no_builder_injected_returns_empty(self) -> None:
        uc = _make_uc("매출 100 130", chart_builder=None)
        charts = await _charts_from_stream(uc, "그래프 그려줘")
        assert charts == []

    async def test_builder_exception_graceful(self) -> None:
        builder = _FakeBuilder(RuntimeError("boom"))
        uc = _make_uc("매출 100 130", chart_builder=builder)
        charts = await _charts_from_stream(uc, "그래프 그려줘")
        assert charts == []  # 예외에도 빈 배열, 흐름 유지


class TestExecuteCharts:
    async def test_execute_surfaces_charts(self) -> None:
        builder = _FakeBuilder([_sample_config()])
        uc = _make_uc("매출 100 130", chart_builder=builder)
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="그래프 그려줘")
        resp = await uc.execute(req, request_id="r1")
        assert len(resp.charts) == 1
        assert resp.charts[0]["type"] == "bar"

    async def test_execute_text_empty_charts(self) -> None:
        uc = _make_uc("간단 설명", chart_builder=_FakeBuilder([_sample_config()]))
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="설명해줘")
        resp = await uc.execute(req, request_id="r1")
        assert resp.charts == []
