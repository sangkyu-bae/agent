"""deep-search-pipeline Design §8.4 L3-6~8 — search 노드 팩토리 배선 (FR-13/D9).

기본값은 legacy이며, deep은 웹검색(tavily) 워커에만 적용된다.
"""
from __future__ import annotations

import pytest

from src.application.agent_builder.workflow_compiler import (
    DEEP_SEARCH_MODE,
    DEEP_SEARCH_TOOL_ID,
    LEGACY_SEARCH_MODE,
    WorkflowCompiler,
)
from src.config import Settings
from src.domain.deep_search.policies import DeepSearchBudgetPolicy


class _StubLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def _log(self, level, message, **kwargs):
        self.records.append((level, message, kwargs))

    def debug(self, message, **kwargs):
        self._log("debug", message, **kwargs)

    def info(self, message, **kwargs):
        self._log("info", message, **kwargs)

    def warning(self, message, **kwargs):
        self._log("warning", message, **kwargs)

    def error(self, message, **kwargs):
        self._log("error", message, **kwargs)

    def has(self, level, needle):
        return any(needle in m for lv, m, _ in self.records if lv == level)


def _compiler(mode: str | None = None, logger=None) -> WorkflowCompiler:
    return WorkflowCompiler(
        tool_factory=object(),
        llm_factory=object(),
        logger=logger or _StubLogger(),
        search_pipeline_mode=mode,
    )


# ── L3-6 ~ L3-8: 모드 해석 ──────────────────────────────────────


def test_l3_6_legacy_mode_selects_legacy_for_web_search():
    """L3-6: mode=legacy면 웹검색도 기존 파이프라인."""
    assert _compiler(LEGACY_SEARCH_MODE)._resolve_search_mode(DEEP_SEARCH_TOOL_ID) \
        == LEGACY_SEARCH_MODE


def test_l3_7_deep_mode_does_not_apply_to_internal_search():
    """L3-7 (AD-3/D9): deep을 켜도 내부 문서검색은 legacy를 탄다."""
    assert _compiler(DEEP_SEARCH_MODE)._resolve_search_mode("internal_document_search") \
        == LEGACY_SEARCH_MODE


def test_deep_mode_applies_to_web_search():
    assert _compiler(DEEP_SEARCH_MODE)._resolve_search_mode(DEEP_SEARCH_TOOL_ID) \
        == DEEP_SEARCH_MODE


@pytest.mark.parametrize("bad", ["depp", "deepsearch", "", "true", "1"])
def test_l3_8_unknown_mode_falls_back_to_legacy_with_warning(bad):
    """L3-8 (FR-13): 알 수 없는 값은 legacy 폴백 + 경고 (조용한 폴백 금지)."""
    logger = _StubLogger()
    compiler = _compiler(bad, logger=logger)
    assert compiler._resolve_search_mode(DEEP_SEARCH_TOOL_ID) == LEGACY_SEARCH_MODE
    assert logger.has("warning", "search_pipeline_mode")


def test_none_mode_is_legacy_without_warning():
    """미주입(None)은 정상적인 하위호환 경로 — 경고를 남기지 않는다."""
    logger = _StubLogger()
    compiler = _compiler(None, logger=logger)
    assert compiler._resolve_search_mode(DEEP_SEARCH_TOOL_ID) == LEGACY_SEARCH_MODE
    assert not logger.has("warning", "search_pipeline_mode")


def test_mode_is_case_and_space_insensitive():
    assert _compiler("  Deep  ")._resolve_search_mode(DEEP_SEARCH_TOOL_ID) \
        == DEEP_SEARCH_MODE


def test_unknown_mode_warns_only_once():
    """컴파일마다 경고가 쌓이지 않도록 생성 시점 1회만 경고한다."""
    logger = _StubLogger()
    compiler = _compiler("depp", logger=logger)
    for _ in range(3):
        compiler._resolve_search_mode(DEEP_SEARCH_TOOL_ID)
    warnings = [m for lv, m, _ in logger.records
                if lv == "warning" and "search_pipeline_mode" in m]
    assert len(warnings) == 1


# ── 팩토리 선택 결과 ────────────────────────────────────────────


def _make_node(compiler: WorkflowCompiler, tool_id: str):
    return compiler._create_search_node(
        worker_id="w1",
        tool_id=tool_id,
        tool=object(),
        llm=object(),
        user_context_block="",
        datetime_block="",
    )


def test_legacy_mode_builds_legacy_node():
    node = _make_node(_compiler(LEGACY_SEARCH_MODE), DEEP_SEARCH_TOOL_ID)
    assert node.__module__ == "src.application.agent_builder.search_pipeline"


def test_deep_mode_builds_deep_node_for_web_search():
    node = _make_node(_compiler(DEEP_SEARCH_MODE), DEEP_SEARCH_TOOL_ID)
    assert node.__module__ == "src.application.deep_search.workflow"


def test_deep_mode_builds_legacy_node_for_internal_search():
    node = _make_node(_compiler(DEEP_SEARCH_MODE), "internal_document_search")
    assert node.__module__ == "src.application.agent_builder.search_pipeline"


def test_deep_node_receives_budget_policy():
    """deep 경로는 SearchPipelinePolicy가 아닌 DeepSearchBudgetPolicy를 받는다."""
    compiler = _compiler(DEEP_SEARCH_MODE)
    assert isinstance(compiler._deep_search_policy(), DeepSearchBudgetPolicy)


# ── config 기본값 (NFR-03 무영향 배포) ──────────────────────────


def test_config_default_mode_is_legacy():
    """기본값이 legacy여야 배포 시 동작이 변하지 않는다 (NFR-03).

    로컬 .env가 deep을 켜 두었을 수 있으므로 런타임 값이 아니라
    **선언된 기본값**을 검사한다 — 환경이 아니라 코드를 검증하기 위함.
    """
    assert Settings.model_fields["search_pipeline_mode"].default == LEGACY_SEARCH_MODE
