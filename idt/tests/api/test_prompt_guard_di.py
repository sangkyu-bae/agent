"""main.py get_prompt_guard() — Design §4.4, FR-10 (탈착형 이음매).

킬스위치 off → None, on → PromptGuardService, judge off → judge=None, 조립 실패 → None.
"""
import pytest
from src.application.prompt_guard.service import PromptGuardService


@pytest.fixture
def main_module(monkeypatch):
    import src.api.main as main

    monkeypatch.setattr(main, "_prompt_guard", None)
    monkeypatch.setattr(main, "_prompt_guard_built", False)
    return main


def test_disabled_returns_none(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "prompt_guard_enabled", False)
    assert main_module.get_prompt_guard() is None


def test_enabled_returns_service_with_judge(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "prompt_guard_enabled", True)
    monkeypatch.setattr(main_module.settings, "prompt_guard_judge_enabled", True)
    guard = main_module.get_prompt_guard()
    assert isinstance(guard, PromptGuardService)
    assert guard._judge is not None
    assert main_module.get_prompt_guard() is guard  # 싱글톤


def test_judge_disabled_builds_service_without_judge(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "prompt_guard_enabled", True)
    monkeypatch.setattr(main_module.settings, "prompt_guard_judge_enabled", False)
    guard = main_module.get_prompt_guard()
    assert isinstance(guard, PromptGuardService)
    assert guard._judge is None


def test_both_chat_use_cases_receive_prompt_guard_kwarg():
    """Check G-7: 두 유스케이스 생성에 prompt_guard=get_prompt_guard() 가 넘어간다.

    런타임 조립은 DB·LLM 이 필요해 여기선 소스 계약으로 고정한다
    (ast-source-contract-tests).
    """
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "src" / "api" / "main.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    wired: dict[str, bool] = {"GeneralChatUseCase": False, "RunAgentUseCase": False}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in wired:
            continue
        for kw in node.keywords:
            is_factory_call = (
                isinstance(kw.value, ast.Call)
                and isinstance(kw.value.func, ast.Name)
                and kw.value.func.id == "get_prompt_guard"
            )
            if kw.arg == "prompt_guard" and is_factory_call:
                wired[node.func.id] = True
    assert wired == {"GeneralChatUseCase": True, "RunAgentUseCase": True}, wired


def test_assembly_failure_returns_none_and_warns(main_module, monkeypatch):
    monkeypatch.setattr(main_module.settings, "prompt_guard_enabled", True)
    # 잘못된 mode → PromptGuardService 생성자 ValueError → 조립 실패 경로
    monkeypatch.setattr(main_module.settings, "prompt_guard_mode", "whatever")
    assert main_module.get_prompt_guard() is None
    assert main_module.get_prompt_guard() is None  # 재시도하지 않고 None 유지
