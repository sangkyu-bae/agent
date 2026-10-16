"""main.py get_judgment_backend() — judgment-backend Design §4.4 / §8.3 #5~7.

off → None, 조립 실패 → None + warning 1회(재시도 없음), 정상 → 어댑터 싱글톤,
그리고 create_analyze_excel_use_case 의 조립 분기는 소스 계약(AST)으로 고정한다.
"""

import ast
from pathlib import Path

import pytest
from src.infrastructure.judgment.anyjev.adapter import AnyJevJudgmentAdapter


@pytest.fixture
def main_module(monkeypatch):
    import src.api.main as main

    monkeypatch.setattr(main, "_judgment_backend", None)
    monkeypatch.setattr(main, "_judgment_backend_built", False)
    return main


def test_off_returns_none(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "judgment_backend", "off")
    assert main_module.get_judgment_backend() is None


def test_anyjev_builds_singleton(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "judgment_backend", "anyjev")
    monkeypatch.setattr(
        main_module.settings, "anyjev_base_url", "http://127.0.0.1:8100"
    )
    backend = main_module.get_judgment_backend()
    assert isinstance(backend, AnyJevJudgmentAdapter)
    assert main_module.get_judgment_backend() is backend


def test_assembly_failure_returns_none_once(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "judgment_backend", "jev")
    monkeypatch.setattr(
        main_module.settings, "typesafe_api_key", None
    )  # 키 없음 → ValueError
    warnings: list = []
    monkeypatch.setattr(
        main_module,
        "get_app_logger",
        lambda: type("L", (), {"warning": lambda self, *a, **k: warnings.append(a)})(),
    )
    assert main_module.get_judgment_backend() is None
    assert main_module.get_judgment_backend() is None
    assert len(warnings) == 1


async def test_close_is_noop_when_disabled(main_module):
    await main_module._close_judgment_backend()


def _main_tree() -> ast.Module:
    src = (Path(__file__).resolve().parents[2] / "src" / "api" / "main.py").read_text(
        encoding="utf-8"
    )
    return ast.parse(src)


def test_search_decision_wiring_contract():
    """조립: JudgmentSearchDecisionAdapter(backend=, fallback=, threshold=, …) 가
    create_analyze_excel_use_case 안에 있다 (소스 계약)."""
    found = {}
    for node in ast.walk(_main_tree()):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "JudgmentSearchDecisionAdapter"
        ):
            found = {kw.arg for kw in node.keywords}
    assert {"backend", "fallback", "threshold", "timeout_seconds", "logger"} <= found, (
        found
    )


def test_lifespan_closes_backend():
    tree = _main_tree()
    lifespan = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan"
    )
    calls = [
        n.func.id
        for n in ast.walk(lifespan)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert "_close_judgment_backend" in calls


def test_search_decision_falls_back_to_llm_when_threshold_invalid(
    main_module, monkeypatch
):
    """Check G5 — 백엔드 on + 임계값 범위 오류는 조립 실패로 흡수(기동 불중단)."""
    from unittest.mock import Mock

    monkeypatch.setattr(main_module.settings, "judgment_backend", "anyjev")
    monkeypatch.setattr(
        main_module.settings, "anyjev_base_url", "http://127.0.0.1:8100"
    )
    monkeypatch.setattr(main_module.settings, "search_decision_judgment_threshold", 1.5)
    llm_adapter = Mock(name="llm_search_decision")
    logger = Mock()
    result = main_module._build_search_decision(llm_adapter, logger)
    assert result is llm_adapter
    logger.warning.assert_called_once()


def test_search_decision_wraps_backend_when_enabled(main_module, monkeypatch):
    """Check G3 — 백엔드가 있으면 JudgmentSearchDecisionAdapter,
    fallback 은 LLM 어댑터."""
    from unittest.mock import Mock

    from src.infrastructure.search_decision.judgment_adapter import (
        JudgmentSearchDecisionAdapter,
    )

    monkeypatch.setattr(main_module.settings, "judgment_backend", "anyjev")
    monkeypatch.setattr(
        main_module.settings, "anyjev_base_url", "http://127.0.0.1:8100"
    )
    llm_adapter = Mock(name="llm_search_decision")
    result = main_module._build_search_decision(llm_adapter, Mock())
    assert isinstance(result, JudgmentSearchDecisionAdapter)
    assert result._fallback is llm_adapter


def test_search_decision_is_llm_adapter_when_off(main_module, monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setattr(main_module.settings, "judgment_backend", "off")
    llm_adapter = Mock(name="llm_search_decision")
    assert main_module._build_search_decision(llm_adapter, Mock()) is llm_adapter
