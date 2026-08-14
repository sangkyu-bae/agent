"""tool-recommender — ToolSelectionMiddleware 어댑터 테스트 (Design §4.3).

미들웨어가 실행을 막지 않는가, request.override로만 좁히는가를 검증한다.
"""
from langchain_core.messages import AIMessage, HumanMessage
from src.domain.tool_selection.schemas import SelectionResult
from src.infrastructure.tool_selection.adapters.selector_middleware import (
    ToolSelectionMiddleware,
    extract_latest_user_text,
)

# ── 테스트 더블 ──────────────────────────────────────────────────────────────


class _Tool:
    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description


class _SpyLogger:
    def __init__(self) -> None:
        self.records = []

    def _rec(self, level, message, **kw):
        self.records.append((level, message, kw))

    def debug(self, m, **kw):
        self._rec("debug", m, **kw)

    def info(self, m, **kw):
        self._rec("info", m, **kw)

    def warning(self, m, **kw):
        self._rec("warning", m, **kw)

    def error(self, m, exception=None, **kw):
        self._rec("error", m, exception=exception, **kw)

    def critical(self, m, exception=None, **kw):
        self._rec("critical", m, exception=exception, **kw)


class _StubSelector:
    def __init__(self, final_ids=(), exc=None) -> None:
        self._final_ids = tuple(final_ids)
        self._exc = exc

    async def select(self, query, candidates, *, required_ids=(), request_id=""):
        if self._exc is not None:
            raise self._exc
        return SelectionResult(
            selected_ids=self._final_ids,
            required_ids=tuple(required_ids),
            final_ids=self._final_ids,
            candidate_count=len(candidates),
        )


class _Request:
    """ModelRequest 흉내 — override가 새 인스턴스를 만드는 것까지 재현."""

    def __init__(self, tools, messages) -> None:
        self.tools = tools
        self.messages = messages

    def override(self, **kwargs):
        clone = _Request(self.tools, self.messages)
        for key, value in kwargs.items():
            setattr(clone, key, value)
        return clone


def _handler_recording(seen: list):
    async def handler(request):
        seen.append(request)
        return AIMessage(content="ok")

    return handler


def _build(selector):
    return ToolSelectionMiddleware(selector, _SpyLogger())


# ── extract_latest_user_text ────────────────────────────────────────────────


def test_extract_returns_last_human_message():
    messages = [
        HumanMessage(content="첫 질문"),
        AIMessage(content="답변"),
        HumanMessage(content="두 번째 질문"),
    ]
    assert extract_latest_user_text(messages) == "두 번째 질문"


def test_extract_ignores_ai_messages():
    assert extract_latest_user_text([AIMessage(content="답변")]) == ""


def test_extract_returns_empty_for_no_messages():
    assert extract_latest_user_text([]) == ""
    assert extract_latest_user_text(None) == ""


def test_extract_handles_multimodal_content_blocks():
    msg = HumanMessage(content=[{"type": "text", "text": "이미지 분석해줘"}])
    assert extract_latest_user_text([msg]) == "이미지 분석해줘"


# ── awrap_model_call ────────────────────────────────────────────────────────


async def test_middleware_narrows_tools_via_override():
    tools = [_Tool("a"), _Tool("b"), _Tool("c")]
    request = _Request(tools, [HumanMessage(content="질의")])
    seen: list = []
    mw = _build(_StubSelector(("internal:a", "internal:b")))

    await mw.awrap_model_call(request, _handler_recording(seen))

    assert [t.name for t in seen[0].tools] == ["a", "b"]
    assert request.tools == tools  # 원본 request는 불변


async def test_middleware_passes_original_request_when_nothing_narrowed():
    tools = [_Tool("a"), _Tool("b")]
    request = _Request(tools, [HumanMessage(content="질의")])
    seen: list = []
    mw = _build(_StubSelector(("internal:a", "internal:b")))

    await mw.awrap_model_call(request, _handler_recording(seen))

    assert seen[0] is request  # override 자체를 하지 않음


async def test_middleware_skips_when_no_tools():
    request = _Request([], [HumanMessage(content="질의")])
    seen: list = []
    mw = _build(_StubSelector(()))

    await mw.awrap_model_call(request, _handler_recording(seen))

    assert seen[0] is request


async def test_middleware_skips_when_no_user_message():
    tools = [_Tool("a"), _Tool("b")]
    request = _Request(tools, [AIMessage(content="답변만 있음")])
    seen: list = []
    mw = _build(_StubSelector(("internal:a",)))

    await mw.awrap_model_call(request, _handler_recording(seen))

    assert seen[0] is request


async def test_middleware_never_blocks_execution_on_selector_failure():
    tools = [_Tool("a"), _Tool("b")]
    request = _Request(tools, [HumanMessage(content="질의")])
    seen: list = []
    mw = _build(_StubSelector(exc=RuntimeError("boom")))

    result = await mw.awrap_model_call(request, _handler_recording(seen))

    assert len(seen) == 1
    assert [t.name for t in seen[0].tools] == ["a", "b"]
    assert result is not None


async def test_middleware_returns_handler_result():
    tools = [_Tool("a"), _Tool("b")]
    request = _Request(tools, [HumanMessage(content="질의")])
    mw = _build(_StubSelector(("internal:a",)))

    result = await mw.awrap_model_call(request, _handler_recording([]))

    assert result.content == "ok"


async def test_middleware_honors_required_ids():
    tools = [_Tool("a"), _Tool("b"), _Tool("c")]
    request = _Request(tools, [HumanMessage(content="질의")])
    seen: list = []
    mw = ToolSelectionMiddleware(
        _StubSelector(("internal:a", "internal:c")),
        _SpyLogger(),
        required_ids=("internal:c",),
    )

    await mw.awrap_model_call(request, _handler_recording(seen))

    assert "c" in [t.name for t in seen[0].tools]
