"""파이프라인 단계 추적 배선 테스트 — Design §8 (T-05~T-07).

협력자 fake 는 `test_use_case` 의 것을 그대로 재사용한다 (빌더 중복 금지).
각 fake 의 실행 시점에 `tracing_v2_callback_var` 를 읽어, 추적 스코프가
**어느 호출 스택까지 닿는지**를 관측한다.

핵심 검증 2가지:
  · T-05 — 스코프가 `yield` 를 가로지르지 않는다 (Design §7-2)
  · T-07 — 파이프라인을 거치지 않는 직접 호출에는 붙지 않는다 (Design §2-2)
"""
import pytest
from langchain_core.tracers.context import tracing_v2_callback_var

from src.application.agent_create_pipeline.events import StageEvent
from src.domain.agent_create_pipeline.stages import PipelineStop
from src.infrastructure.langsmith.langsmith import PIPELINE_PROJECT_NAME

from tests.application.agent_create_pipeline.test_use_case import (
    FakeComposeUC,
    FakeIntentUC,
    FakeSelector,
    _compose_result,
    _drain,
    _intent_ok,
    _pipeline,
    _selection,
)

_DUMMY_KEY = "lsv2_dummy_key_for_test"


@pytest.fixture(autouse=True)
def with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGCHAIN_API_KEY", _DUMMY_KEY)


def _observed_tags() -> list[str] | None:
    """지금 이 호출 스택에 걸린 추적 태그 (없으면 None)."""
    tracer = tracing_v2_callback_var.get()
    return None if tracer is None else list(tracer.tags or [])


def _observed_project() -> str | None:
    tracer = tracing_v2_callback_var.get()
    return None if tracer is None else tracer.project_name


# ── 관측용 fake (협력자 실행 시점의 스코프를 기록) ──────────────────────────


class SpyIntentUC(FakeIntentUC):
    def __init__(self) -> None:
        super().__init__(_intent_ok())
        self.seen_tags: list[str] | None = None
        self.seen_project: str | None = None

    async def execute(self, **kwargs):
        self.seen_tags = _observed_tags()
        self.seen_project = _observed_project()
        return await super().execute(**kwargs)


class SpySelector(FakeSelector):
    def __init__(self) -> None:
        super().__init__(_selection())
        self.seen_tags: list[str] | None = None

    async def select(self, query, candidates, **kwargs):
        self.seen_tags = _observed_tags()
        return await super().select(query, candidates, **kwargs)


class SpyComposeUC(FakeComposeUC):
    def __init__(self) -> None:
        super().__init__(_compose_result())
        self.seen_tags: list[str] | None = None

    async def compose(self, **kwargs):
        self.seen_tags = _observed_tags()
        return await super().compose(**kwargs)


def _spy_pipeline():
    intent, selector, compose = SpyIntentUC(), SpySelector(), SpyComposeUC()
    use_case, _ = _pipeline(intent=intent, compose=compose)
    # _pipeline 은 selector 를 selection 인자로만 받으므로 직접 교체한다.
    use_case._selector = selector
    return use_case, intent, selector, compose


# ── T-06: 세 LLM 단계 모두 추적 스코프 안에서 실행된다 ──────────────────────


class TestStageScopeReachesCollaborators:
    """Design §4-1 — `_stage()` 한 곳이 5단계를 전부 덮는지 확인."""

    async def test_intent_stage_is_traced(self) -> None:
        use_case, intent, _, _ = _spy_pipeline()
        await _drain(use_case, request_id="req-t6")
        assert intent.seen_project == PIPELINE_PROJECT_NAME
        assert "stage:intent" in intent.seen_tags
        assert "request:req-t6" in intent.seen_tags

    async def test_tools_stage_is_traced(self) -> None:
        use_case, _, selector, _ = _spy_pipeline()
        await _drain(use_case, request_id="req-t6")
        assert "stage:tools" in selector.seen_tags

    async def test_prompt_stage_is_traced(self) -> None:
        use_case, _, _, compose = _spy_pipeline()
        await _drain(use_case, request_id="req-t6")
        assert "stage:prompt" in compose.seen_tags

    async def test_each_stage_gets_its_own_tag(self) -> None:
        """단계마다 스코프가 새로 열린다 — 태그가 서로 달라야 한다."""
        use_case, intent, selector, compose = _spy_pipeline()
        await _drain(use_case, request_id="req-t6")
        assert intent.seen_tags != selector.seen_tags != compose.seen_tags

    async def test_round_and_stop_propagate(self) -> None:
        use_case, intent, _, _ = _spy_pipeline()
        await _drain(
            use_case, request_id="req-t6", round_=2,
            stop_after=PipelineStop.TOOLS,
        )
        assert "round:2" in intent.seen_tags
        assert "stop:tools" in intent.seen_tags


# ── T-05: 스코프가 yield 를 가로지르지 않는다 (Design §7-2) ─────────────────


class TestScopeDoesNotCrossYield:
    """contextvar × async generator 함정 고정.

    `_stage()` 의 `with` 가 `yield` 를 감싸면 소비자(여기서는 테스트)가
    제너레이터를 재개시키는 동안 추적 스코프가 소비자 쪽으로 샌다.
    """

    async def test_consumer_never_sees_tracer(self) -> None:
        use_case, _, _, _ = _spy_pipeline()
        leaked: list[str] = []

        async for event in use_case.run(
            user_id="u1", user_request="검색 에이전트 만들어줘",
            request_id="req-t5",
        ):
            if tracing_v2_callback_var.get() is not None:
                kind = getattr(event, "kind", type(event).__name__)
                leaked.append(kind)

        assert leaked == [], f"추적 스코프가 소비자로 샜다: {leaked}"

    async def test_scope_closed_after_run(self) -> None:
        use_case, _, _, _ = _spy_pipeline()
        await _drain(use_case, request_id="req-t5")
        assert tracing_v2_callback_var.get() is None

    async def test_scope_closed_even_when_stage_raises(self) -> None:
        """예외 전파가 계약(use_case §6.2)이므로 스코프도 정리돼야 한다."""
        compose = SpyComposeUC()
        compose.compose_error = RuntimeError("prompt boom")
        use_case, _ = _pipeline(compose=compose)

        with pytest.raises(RuntimeError):
            await _drain(use_case, request_id="req-t5")
        assert tracing_v2_callback_var.get() is None


# ── T-07: 파이프라인 밖 호출에는 붙지 않는다 (Design §2-2) ──────────────────


class TestSharedSingletonIsolation:
    """`_intent_use_case` / `_prompt_f` 는 독립 라우터와 공유되는 싱글턴이다.

    어댑터 내부에서 tracer 를 만들었다면(Option A) 독립 호출까지 파이프라인으로
    오분류된다. 스코프 방식은 호출 스택 단위라 그 일이 구조적으로 없다.
    """

    async def test_direct_intent_call_is_not_traced(self) -> None:
        """같은 인스턴스를 파이프라인 없이 직접 부르면 추적되지 않는다."""
        use_case, intent, _, _ = _spy_pipeline()
        await _drain(use_case, request_id="req-t7")
        assert intent.seen_tags is not None  # 파이프라인 경유는 추적됨

        intent.seen_tags = None
        await intent.execute(
            message="직접 호출", spec=None, request_id="direct-1",
        )
        assert intent.seen_tags is None

    async def test_direct_compose_call_is_not_traced(self) -> None:
        use_case, _, _, compose = _spy_pipeline()
        await _drain(use_case, request_id="req-t7")
        assert compose.seen_tags is not None

        compose.seen_tags = None
        await compose.compose(
            user_id="u1", user_request="직접 호출", request_id="direct-1",
        )
        assert compose.seen_tags is None


# ── 회귀: 추적이 이벤트 계약을 바꾸지 않는다 ────────────────────────────────


class TestNoBehaviourChange:
    async def test_event_sequence_unchanged(self) -> None:
        use_case, _, _, _ = _spy_pipeline()
        events = await _drain(use_case, request_id="req-reg")
        kinds = [e.kind for e in events if isinstance(e, StageEvent)]
        assert kinds == [
            kind for _ in range(5)
            for kind in ("stage_started", "stage_completed")
        ]

    async def test_works_without_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plan SC-05 — 키 없는 환경에서도 파이프라인이 정상 동작한다."""
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
        use_case, intent, _, _ = _spy_pipeline()
        events = await _drain(use_case, request_id="req-nokey")
        assert intent.seen_tags is None
        assert len([e for e in events if isinstance(e, StageEvent)]) == 10
