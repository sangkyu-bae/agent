"""계약: LLM 응답 content는 문자열로 정규화해서 읽는다.

thinking이 켜진 모델(Claude Opus 5.5 등)은 AIMessage.content가 문자열이 아니라
블록 리스트(thinking + text)다. `.strip()`·JSON 파싱·`str()`을 바로 하면
AttributeError로 그래프가 멈추거나 블록 repr이 사용자에게 나간다
(2026-11-19 엑셀 생성기 실 LLM 스모크에서 발견).

규칙: 응답 변수(response/resp/ai_message)의 `.content` 또는
`getattr(<응답>, "content", ...)`는 정규화 함수 호출의 인자로만 읽는다.
"""
import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
_RESPONSE_NAMES = {"response", "resp", "ai_message"}
_COERCERS = {"coerce_message_text", "_coerce_text"}


def _is_response_content(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        return (
            node.attr == "content"
            and isinstance(node.value, ast.Name)
            and node.value.id in _RESPONSE_NAMES
        )
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "getattr":
        args = node.args
        return (
            len(args) >= 2
            and isinstance(args[0], ast.Name)
            and args[0].id in _RESPONSE_NAMES
            and isinstance(args[1], ast.Constant)
            and args[1].value == "content"
        )
    return False


def _coerced_nodes(tree: ast.AST) -> set[int]:
    wrapped: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in _COERCERS:
            wrapped.update(id(arg) for arg in node.args)
    return wrapped


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wrapped = _coerced_nodes(tree)
    found = []
    for node in ast.walk(tree):
        if _is_response_content(node) and id(node) not in wrapped:
            found.append(f"{path.relative_to(_SRC.parent)}:{node.lineno}")
    return found


def test_llm_response_content_is_always_coerced():
    violations = [v for path in sorted(_SRC.rglob("*.py")) for v in _violations(path)]
    assert violations == [], (
        "LLM 응답 content를 정규화 없이 읽는 곳이 있습니다. "
        "src.domain.llm.message_content.coerce_message_text(...)로 감싸세요:\n"
        + "\n".join(violations)
    )
