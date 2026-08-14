"""create_intent_node 단위 테스트 — 탈착 이음매 검증.

Design §8.2 시나리오 16~19. 이 파일이 검증하는 두 계약이 기능의 존재 이유다:
  1. analyzer 미주입 → None 반환 → 호출측이 add_node 자체를 건너뛴다 (FR-09)
  2. 반환 dict 의 키가 state_key 단 1개 — 다른 state 를 오염시키지 않는다 (FR-08)

계약 2 는 위키 계약 1(워커 산출물 = AIMessage 1건)과도 맞물린다. intent 노드는
워커가 아니므로 messages 를 만들면 안 된다.
"""
from typing import Any

from src.application.intent.node import create_intent_node
from src.domain.intent.interfaces import IntentAnalyzerInterface
from src.domain.intent.schemas import IntentLabel, IntentResult, IntentSpec, Turn


class RecordingLogger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def debug(self, message: str, **kwargs: Any) -> None:
        self.calls.append(("debug", message, kwargs))

    def info(self, message: str, **kwargs: Any) -> None:
        self.calls.append(("info", message, kwargs))

    def warning(self, message: str, **kwargs: Any) -> None:
        self.calls.append(("warning", message, kwargs))

    def error(
        self, message: str, exception: Exception | None = None, **kwargs: Any
    ) -> None:
        self.calls.append(("error", message, {"exception": exception, **kwargs}))

    def critical(
        self, message: str, exception: Exception | None = None, **kwargs: Any
    ) -> None:
        self.calls.append(("critical", message, {"exception": exception, **kwargs}))


class StubAnalyzer(IntentAnalyzerInterface):
    def __init__(self, result: IntentResult | None = None) -> None:
        self.result = result or IntentResult(label="search", confidence=0.8)
        self.calls: list[dict[str, Any]] = []

    async def analyze(
        self,
        message: str,
        spec: IntentSpec,
        history: list[Turn] | None = None,
        request_id: str = "",
    ) -> IntentResult:
        self.calls.append({"message": message, "history": history})
        return self.result


def _spec() -> IntentSpec:
    return IntentSpec(
        labels=[
            IntentLabel(name="search", description="근거 문서를 찾아야 하는 질문"),
            IntentLabel(name="analysis", description="데이터를 계산·비교하는 질문"),
        ]
    )


# --- 시나리오 16: 미주입 → None (탈착의 핵심) -------------------------------


def test_factory_returns_none_when_analyzer_missing() -> None:
    node = create_intent_node(analyzer=None, spec=_spec(), logger=RecordingLogger())

    assert node is None, "호출측이 add_node 를 건너뛸 수 있어야 한다"


def test_factory_returns_callable_when_analyzer_present() -> None:
    node = create_intent_node(
        analyzer=StubAnalyzer(), spec=_spec(), logger=RecordingLogger()
    )

    assert node is not None
    assert callable(node)


# --- 시나리오 17: state 오염 금지 -------------------------------------------


async def test_node_returns_only_the_state_key() -> None:
    node = create_intent_node(
        analyzer=StubAnalyzer(), spec=_spec(), logger=RecordingLogger()
    )
    assert node is not None

    patch = await node({"messages": [], "question": "여신 규정 알려줘"})

    assert set(patch.keys()) == {"intent"}, "다른 state 키를 건드리면 안 된다"


async def test_node_does_not_emit_messages() -> None:
    """intent 노드는 워커가 아니므로 messages 를 만들지 않는다 (위키 계약 1)."""
    node = create_intent_node(
        analyzer=StubAnalyzer(), spec=_spec(), logger=RecordingLogger()
    )
    assert node is not None

    patch = await node({"messages": [], "question": "여신 규정"})

    assert "messages" not in patch


async def test_node_payload_is_serializable_dict() -> None:
    node = create_intent_node(
        analyzer=StubAnalyzer(), spec=_spec(), logger=RecordingLogger()
    )
    assert node is not None

    patch = await node({"question": "여신 규정"})

    assert isinstance(patch["intent"], dict)
    assert patch["intent"]["label"] == "search"


# --- 시나리오 18: state_key 커스터마이즈 -------------------------------------


async def test_custom_state_key_is_used() -> None:
    node = create_intent_node(
        analyzer=StubAnalyzer(),
        spec=_spec(),
        logger=RecordingLogger(),
        state_key="my_intent",
    )
    assert node is not None

    patch = await node({"question": "여신 규정"})

    assert set(patch.keys()) == {"my_intent"}


# --- 시나리오 19: degraded 도 조용히 기록 ------------------------------------


async def test_degraded_result_is_recorded_without_raising() -> None:
    node = create_intent_node(
        analyzer=StubAnalyzer(result=IntentResult(degraded=True)),
        spec=_spec(),
        logger=RecordingLogger(),
    )
    assert node is not None

    patch = await node({"question": "여신 규정"})

    assert patch["intent"]["degraded"] is True
    assert patch["intent"]["label"] is None


# --- 메시지 추출 -------------------------------------------------------------


async def test_message_is_read_from_question_key() -> None:
    analyzer = StubAnalyzer()
    node = create_intent_node(
        analyzer=analyzer, spec=_spec(), logger=RecordingLogger()
    )
    assert node is not None

    await node({"question": "여신 한도 알려줘"})

    assert analyzer.calls[0]["message"] == "여신 한도 알려줘"


async def test_missing_message_yields_degraded_without_calling_analyzer() -> None:
    """판정할 메시지가 없으면 LLM 을 부르지 않고 degraded 로 넘어간다 (비용 방어)."""
    analyzer = StubAnalyzer()
    node = create_intent_node(
        analyzer=analyzer, spec=_spec(), logger=RecordingLogger()
    )
    assert node is not None

    patch = await node({"messages": []})

    assert patch["intent"]["degraded"] is True
    assert analyzer.calls == []


async def test_history_key_none_forwards_no_history() -> None:
    """history_key 를 주지 않으면 이력 없이 판정한다 (기본값)."""
    analyzer = StubAnalyzer()
    node = create_intent_node(
        analyzer=analyzer, spec=_spec(), logger=RecordingLogger()
    )
    assert node is not None

    await node({"question": "여신 규정", "history": [{"role": "user", "content": "x"}]})

    assert analyzer.calls[0]["history"] is None, "history_key 미지정 시 무시한다"


async def test_history_key_converts_dicts_to_turns() -> None:
    analyzer = StubAnalyzer()
    node = create_intent_node(
        analyzer=analyzer,
        spec=_spec(),
        logger=RecordingLogger(),
        history_key="chat_history",
    )
    assert node is not None

    await node(
        {
            "question": "그거 말고",
            "chat_history": [
                {"role": "user", "content": "여신 규정"},
                {"role": "assistant", "content": "어떤 부분을요?"},
            ],
        }
    )

    history = analyzer.calls[0]["history"]
    assert history is not None
    assert [turn.role for turn in history] == ["user", "assistant"]
    assert history[0].content == "여신 규정"


async def test_history_key_accepts_turn_objects_as_is() -> None:
    analyzer = StubAnalyzer()
    node = create_intent_node(
        analyzer=analyzer,
        spec=_spec(),
        logger=RecordingLogger(),
        history_key="chat_history",
    )
    assert node is not None
    turns = [Turn(role="user", content="여신 규정")]

    await node({"question": "그거 말고", "chat_history": turns})

    assert analyzer.calls[0]["history"] == turns


async def test_history_key_drops_malformed_items() -> None:
    """형식이 다른 항목은 조용히 버린다 — 이력 오염이 판정을 막으면 안 된다."""
    analyzer = StubAnalyzer()
    node = create_intent_node(
        analyzer=analyzer,
        spec=_spec(),
        logger=RecordingLogger(),
        history_key="chat_history",
    )
    assert node is not None

    await node(
        {
            "question": "그거 말고",
            "chat_history": [
                {"role": "user", "content": "여신 규정"},
                {"role": "system", "content": "허용되지 않는 role"},
                "문자열은 턴이 아니다",
                {"content": "role 누락"},
            ],
        }
    )

    history = analyzer.calls[0]["history"]
    assert history is not None
    assert len(history) == 1
    assert history[0].content == "여신 규정"


async def test_history_key_with_all_items_invalid_yields_none() -> None:
    analyzer = StubAnalyzer()
    node = create_intent_node(
        analyzer=analyzer,
        spec=_spec(),
        logger=RecordingLogger(),
        history_key="chat_history",
    )
    assert node is not None

    await node({"question": "여신 규정", "chat_history": ["엉망", 42]})

    assert analyzer.calls[0]["history"] is None


async def test_history_key_with_non_list_value_yields_none() -> None:
    analyzer = StubAnalyzer()
    node = create_intent_node(
        analyzer=analyzer,
        spec=_spec(),
        logger=RecordingLogger(),
        history_key="chat_history",
    )
    assert node is not None

    await node({"question": "여신 규정", "chat_history": "리스트가 아님"})

    assert analyzer.calls[0]["history"] is None


async def test_custom_message_key_is_supported() -> None:
    analyzer = StubAnalyzer()
    node = create_intent_node(
        analyzer=analyzer,
        spec=_spec(),
        logger=RecordingLogger(),
        message_key="user_input",
    )
    assert node is not None

    await node({"user_input": "여신 규정"})

    assert analyzer.calls[0]["message"] == "여신 규정"
