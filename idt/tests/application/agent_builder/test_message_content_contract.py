"""message content 접근 계약 테스트 — chat-image-attachment Design §8.2 #20 / D-02.

상태 메시지 content 는 str | list(block) 다. agent_builder·agent_run 안에서
content 를 직접 꺼내 문자열로 다루는 패턴을 금지하고, 반드시
`src.application.agent_builder.message_content.message_text` 를 거치게 한다.

금지 패턴 (AST):
- getattr(<expr>, "content", ...)
- <expr>.get("content", ...)
- <expr>.content  (속성 읽기 — Analysis G-I4 로 추가)
- def _message_text / def _extract_content  (사설 헬퍼 재정의)
허용: 헬퍼 모듈 자신.
"""
import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "application"
PACKAGES = [SRC / "agent_builder", SRC / "agent_run"]
ALLOWED = {SRC / "agent_builder" / "message_content.py"}
FORBIDDEN_DEFS = {"_message_text", "_extract_content"}


def _py_files() -> list[Path]:
    files: list[Path] = []
    for pkg in PACKAGES:
        files += sorted(p for p in pkg.rglob("*.py") if p not in ALLOWED)
    return files


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            found += _call_violation(node)
        elif (
            isinstance(node, ast.Attribute)
            and node.attr == "content"
            and isinstance(node.ctx, ast.Load)
        ):
            found.append(f"L{node.lineno}: .content 속성 읽기")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in FORBIDDEN_DEFS:
                found.append(f"L{node.lineno}: def {node.name}")
    return found


def _call_violation(node: ast.Call) -> list[str]:
    fn = node.func
    first = node.args[0] if node.args else None
    key = (
        first.value if isinstance(first, ast.Constant) and isinstance(first.value, str)
        else None
    )
    if isinstance(fn, ast.Name) and fn.id == "getattr" and len(node.args) >= 2:
        second = node.args[1]
        if isinstance(second, ast.Constant) and second.value == "content":
            return [f'L{node.lineno}: getattr(..., "content")']
    if isinstance(fn, ast.Attribute) and fn.attr == "get" and key == "content":
        return [f'L{node.lineno}: .get("content")']
    return []


@pytest.mark.parametrize("path", _py_files(), ids=lambda p: str(p.relative_to(SRC)))
def test_no_direct_content_access(path: Path) -> None:
    violations = _violations(path)
    assert not violations, (
        f"{path.relative_to(SRC)} 에서 content 직접 접근: {violations}. "
        "message_content.message_text() 를 사용하세요."
    )
