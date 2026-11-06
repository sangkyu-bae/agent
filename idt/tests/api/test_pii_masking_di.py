"""pii-masking-integration module-3 — main.py DI 테스트 (Design §6.2, D-02, D-03, D-06).

prompt guard와 달리 on 모드 조립 실패는 조용히 끄지 않고 올린다. 보호를 켰다고
믿는 상태에서 경계가 빠지는 쪽이 더 위험하기 때문이다(prompt guard G-10 교훈).
"""

import ast
from pathlib import Path

import pytest
from src.application.pii_masking.message_masker import PiiMessageMasker
from src.domain.pii_masking.schemas import PiiMaskingMode

MAIN = Path(__file__).resolve().parents[2] / "src" / "api" / "main.py"


@pytest.fixture
def main_module(monkeypatch):
    import src.api.main as main

    monkeypatch.setattr(main, "_pii_masker", None)
    monkeypatch.setattr(main, "_pii_masker_built", False)
    monkeypatch.setattr(main.settings, "pii_masking_enabled", True)
    monkeypatch.setattr(main.settings, "pii_masking_mode", "shadow")
    monkeypatch.setattr(
        main.settings, "pii_masking_types", "rrn,phone,email,card,account"
    )
    monkeypatch.setattr(main.settings, "langsmith_tracing", False)
    return main


def test_disabled_returns_none(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "pii_masking_enabled", False)
    assert main_module.get_pii_masker() is None


def test_enabled_returns_singleton_masker_with_configured_mode(main_module):
    masker = main_module.get_pii_masker()
    assert isinstance(masker, PiiMessageMasker)
    assert masker.new_scope().mode is PiiMaskingMode.SHADOW
    assert main_module.get_pii_masker() is masker


def test_inspector_follows_masker(main_module, monkeypatch):
    from src.domain.pii_masking.interfaces import PiiInspectPort

    assert isinstance(main_module.get_pii_inspector(), PiiInspectPort)
    monkeypatch.setattr(main_module, "_pii_masker", None)
    monkeypatch.setattr(main_module, "_pii_masker_built", False)
    monkeypatch.setattr(main_module.settings, "pii_masking_enabled", False)
    assert main_module.get_pii_inspector() is None


def test_guarded_factory_returns_raw_when_disabled(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "pii_masking_enabled", False)
    raw = object()
    assert main_module._pii_llm_factory.guard(raw) is raw


def test_on_mode_assembly_failure_raises(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "pii_masking_mode", "on")
    monkeypatch.setattr(main_module.settings, "pii_masking_types", "rrn,phon")
    with pytest.raises(ValueError):
        main_module.get_pii_masker()


def test_shadow_mode_assembly_failure_returns_none(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "pii_masking_types", "rrn,phon")
    assert main_module.get_pii_masker() is None
    assert main_module.get_pii_masker() is None  # 재시도하지 않는다


def test_tracing_with_on_mode_warns(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "pii_masking_mode", "on")
    monkeypatch.setattr(main_module.settings, "langsmith_tracing", True)
    assert main_module._pii_tracing_conflict() is True


def test_tracing_with_masking_disabled_does_not_warn(main_module, monkeypatch):
    # Check G-6: 킬스위치가 꺼져 있으면 마스킹 자체가 없으므로 경고하지 않는다.
    monkeypatch.setattr(main_module.settings, "pii_masking_enabled", False)
    monkeypatch.setattr(main_module.settings, "pii_masking_mode", "on")
    monkeypatch.setattr(main_module.settings, "langsmith_tracing", True)
    assert main_module._pii_tracing_conflict() is False


def test_tracing_with_shadow_mode_does_not_warn(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "langsmith_tracing", True)
    assert main_module._pii_tracing_conflict() is False


def _calls_with_kwarg(tree, class_name: str, kwarg: str, factory: str) -> list[bool]:
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != class_name:
            continue
        found.append(
            any(
                kw.arg == kwarg
                and isinstance(kw.value, ast.Call)
                and isinstance(kw.value.func, ast.Name)
                and kw.value.func.id == factory
                for kw in node.keywords
            )
        )
    return found


def test_compiler_and_run_agent_receive_pii_masker():
    """소스 계약 — 런타임 조립은 DB·LLM이 필요해 AST로 고정한다."""
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    compiler = _calls_with_kwarg(
        tree, "WorkflowCompiler", "pii_masker", "get_pii_masker"
    )
    run_agent = _calls_with_kwarg(
        tree, "RunAgentUseCase", "pii_masker", "get_pii_masker"
    )
    assert compiler and all(compiler), compiler
    assert run_agent and all(run_agent), run_agent


def test_lifespan_assembles_pii_masker_at_startup():
    """D-02 — on 모드 설정 오류는 첫 요청이 아니라 기동 시점에 드러나야 한다."""
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    lifespan = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan"
    )
    names = {
        n.func.id
        for n in ast.walk(lifespan)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "get_pii_masker" in names
