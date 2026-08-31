"""runtime-datetime-context D3 — main.py 배선 계약 (AST 소스 계약 테스트).

`agent_timezone` 소비자 4종의 생성자 호출이 전부 `settings.agent_timezone` 을
주입하는지 본다. kwarg 기본값이 None(블록 생략)이라 배선 누락은 테스트·타입
어느 쪽에도 안 잡힌다 — 프로덕션에서 조용히 날짜가 빠지는 유일한 경로를 여기서 막는다.
DB/외부 클라이언트 없이 결정적으로 검증하기 위해 실인스턴스 대신 소스를 본다
(wiki: ast-source-contract-tests).
"""
import ast
from pathlib import Path

import pytest

_MAIN = Path(__file__).resolve().parents[2] / "src" / "api" / "main.py"
_CONSUMERS = (
    "WorkflowCompiler",
    "GeneralChatUseCase",
    "RAGAgentUseCase",
    "ExcelAnalysisWorkflow",
)


def _callee_name(func: ast.expr) -> str | None:
    """`Cls(...)` 와 `mod.Cls(...)` 두 호출 형태 모두 인식 (모듈 경유 리팩터 대비)."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _constructor_calls(class_name: str) -> list[ast.Call]:
    tree = ast.parse(_MAIN.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _callee_name(node.func) == class_name
    ]


def _is_settings_agent_timezone(value: ast.expr) -> bool:
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "agent_timezone"
        and isinstance(value.value, ast.Name)
        and value.value.id == "settings"
    )


def test_main_imports_settings_from_config():
    """`settings` 식별자 자체가 `src.config` 의 것임을 고정 — 변수명만 바꿔치기 방지."""
    tree = ast.parse(_MAIN.read_text(encoding="utf-8"))
    imported = [
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "src.config"
        for alias in node.names
    ]
    assert "settings" in imported


@pytest.mark.parametrize("class_name", _CONSUMERS)
def test_main_wires_settings_agent_timezone(class_name: str):
    calls = _constructor_calls(class_name)
    assert calls, f"{class_name} 생성 호출이 main.py 에 없음"
    for call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        assert "agent_timezone" in kw, (
            f"{class_name}(...) line {call.lineno}: agent_timezone 미주입"
        )
        assert _is_settings_agent_timezone(kw["agent_timezone"]), (
            f"{class_name}(...) line {call.lineno}: settings.agent_timezone 이어야 함"
        )
