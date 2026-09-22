"""파이프라인 단계 스코프 추적 컨텍스트 단위 테스트.

Design Ref: pipeline-langsmith-tracing §3-1 / §8 (T-01~T-04).

C-2(contextvar) 채택 근거는 Design §1-2 — domain Port 시그니처를 건드리지 않고
`langchain_core.tracers.context.tracing_v2_enabled` 의 contextvar 로 단계 스코프를
연다. 따라서 검증도 `tracing_v2_callback_var` 를 직접 읽어서 한다.
"""
import pytest
from langchain_core.tracers.context import tracing_v2_callback_var

from src.domain.agent_create_pipeline.stages import PipelineStage, PipelineStop
from src.infrastructure.langsmith.langsmith import (
    PIPELINE_PROJECT_NAME,
    pipeline_tracing,
)

_DUMMY_KEY = "lsv2_dummy_key_for_test"


@pytest.fixture
def no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)


@pytest.fixture
def with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGCHAIN_API_KEY", _DUMMY_KEY)


def _tracer():
    """현재 스코프에 걸린 추적기 (없으면 None)."""
    return tracing_v2_callback_var.get()


class TestKeyGuard:
    """T-01 — 키가 없으면 추적을 아예 열지 않는다 (Plan SC-05 / Design §7-1).

    tracing_v2_enabled 는 키가 없어도 진입하고 tracer 를 만든다(Design §1-3 실측).
    그대로 쓰면 키 없는 배포가 전송을 시도하므로 진입 전 가드가 필요하다.
    """

    def test_no_tracer_without_key(self, no_key: None) -> None:
        with pipeline_tracing(PipelineStage.PROMPT, request_id="r-1"):
            assert _tracer() is None

    def test_body_still_runs_without_key(self, no_key: None) -> None:
        ran = False
        with pipeline_tracing(PipelineStage.INTENT, request_id="r-1"):
            ran = True
        assert ran is True


class TestScope:
    """T-02 — 키가 있으면 컨텍스트 안에서만 추적기가 보인다."""

    def test_tracer_inside_only(self, with_key: None) -> None:
        assert _tracer() is None
        with pipeline_tracing(PipelineStage.TOOLS, request_id="r-1"):
            assert _tracer() is not None
        assert _tracer() is None

    def test_uses_pipeline_project(self, with_key: None) -> None:
        with pipeline_tracing(PipelineStage.TOOLS, request_id="r-1"):
            assert _tracer().project_name == PIPELINE_PROJECT_NAME

    def test_restores_previous_scope(self, with_key: None) -> None:
        """중첩 시 바깥 스코프가 복원된다 (단계별 열고 닫기의 전제)."""
        with pipeline_tracing(PipelineStage.INTENT, request_id="r-1"):
            outer = _tracer()
            with pipeline_tracing(PipelineStage.PROMPT, request_id="r-1"):
                assert _tracer() is not outer
            assert _tracer() is outer


class TestTags:
    """T-03 — 태그로 단계·요청·라운드를 구분한다.

    Design §7-3 — tracing_v2_enabled 는 run_name/metadata 를 받지 않으므로
    Plan 의 run_name·metadata 요구를 태그로 대체한다.
    """

    def test_common_and_stage_tags(self, with_key: None) -> None:
        with pipeline_tracing(PipelineStage.PROMPT, request_id="req-9"):
            tags = _tracer().tags
        assert "agent-create-pipeline" in tags
        assert "stage:prompt" in tags

    def test_request_tag_enables_grouping(self, with_key: None) -> None:
        """Plan SC-02 — 한 요청의 여러 단계를 묶어 조회할 수 있어야 한다."""
        with pipeline_tracing(PipelineStage.INTENT, request_id="req-9"):
            intent_tags = _tracer().tags
        with pipeline_tracing(PipelineStage.TOOLS, request_id="req-9"):
            tools_tags = _tracer().tags
        assert "request:req-9" in intent_tags
        assert "request:req-9" in tools_tags

    def test_round_and_stop_tags(self, with_key: None) -> None:
        with pipeline_tracing(
            PipelineStage.INTENT,
            request_id="r-1",
            round_=2,
            stop_after=PipelineStop.TOOLS,
        ):
            tags = _tracer().tags
        assert "round:2" in tags
        assert "stop:tools" in tags

    def test_stop_tag_when_nonstop(self, with_key: None) -> None:
        with pipeline_tracing(PipelineStage.CREATE, request_id="r-1"):
            tags = _tracer().tags
        assert "stop:none" in tags


class TestDegradeOnFailure:
    """T-04 — 추적 설정이 실패해도 파이프라인을 중단시키지 않는다 (Plan NFR-01)."""

    def test_falls_back_when_tracing_raises(
        self, with_key: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("langsmith unavailable")

        monkeypatch.setattr(
            "src.infrastructure.langsmith.langsmith.tracing_v2_enabled", boom
        )
        ran = False
        with pipeline_tracing(PipelineStage.PROMPT, request_id="r-1"):
            ran = True
            assert _tracer() is None
        assert ran is True

    def test_body_exception_propagates(self, with_key: None) -> None:
        """본문 예외는 삼키지 않는다 — use_case 의 '예외 전파가 계약'(§6.2)."""
        with pytest.raises(ValueError):
            with pipeline_tracing(PipelineStage.PROMPT, request_id="r-1"):
                raise ValueError("stage failed")
        assert _tracer() is None
