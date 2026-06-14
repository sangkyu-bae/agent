"""WorkflowCompiler search 파이프라인 wiring 테스트 (Design §4-3).

파이프라인 자체 동작은 test_search_pipeline.py에서 검증.
여기서는 경량 LLM 해석(_resolve_pipeline_llm)과 하위호환 fallback만 검증한다.
(기존 _create_search_node 직접 테스트 TC-S01~S05는 파이프라인 도입으로
test_search_pipeline.py의 동등 케이스로 대체됨.)
"""
from unittest.mock import MagicMock

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.infrastructure.agent_builder.tool_factory import ToolFactory


def _make_compiler(pipeline_llm_model=None) -> WorkflowCompiler:
    tool_factory = MagicMock(spec=ToolFactory)
    llm_factory = MagicMock()
    logger = MagicMock()
    return WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=logger,
        pipeline_llm_model=pipeline_llm_model,
    )


class TestResolvePipelineLlm:
    def test_none_model_returns_run_llm(self):
        """미주입 시 per-run LLM 그대로 (하위호환)."""
        compiler = _make_compiler(pipeline_llm_model=None)
        run_llm = object()

        assert compiler._resolve_pipeline_llm(run_llm) is run_llm
        compiler._llm_factory.create.assert_not_called()

    def test_injected_model_creates_lightweight_llm(self):
        model = MagicMock(provider="openai", model_name="gpt-4o-mini")
        compiler = _make_compiler(pipeline_llm_model=model)
        created = object()
        compiler._llm_factory.create.return_value = created

        assert compiler._resolve_pipeline_llm(object()) is created
        compiler._llm_factory.create.assert_called_once_with(model, 0.0)

    def test_created_llm_is_cached(self):
        model = MagicMock(provider="openai", model_name="gpt-4o-mini")
        compiler = _make_compiler(pipeline_llm_model=model)
        compiler._llm_factory.create.return_value = object()

        first = compiler._resolve_pipeline_llm(object())
        second = compiler._resolve_pipeline_llm(object())

        assert first is second
        assert compiler._llm_factory.create.call_count == 1

    def test_creation_failure_falls_back_to_run_llm(self):
        """API 키 부재 등 생성 실패 → warning + per-run LLM fallback (D3)."""
        model = MagicMock(provider="openai", model_name="gpt-4o-mini")
        compiler = _make_compiler(pipeline_llm_model=model)
        compiler._llm_factory.create.side_effect = RuntimeError("no api key")
        run_llm = object()

        assert compiler._resolve_pipeline_llm(run_llm) is run_llm
        compiler._logger.warning.assert_called_once()
