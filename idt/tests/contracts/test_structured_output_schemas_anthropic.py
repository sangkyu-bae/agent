"""계약: LLM이 보는 구조화 출력 스키마는 Anthropic json_schema 방식과 호환돼야 한다.

claude-agent-e2e-fixes Design §5.3 (FR-11). 강제 tool_choice 를 거부하는 Claude 모델
(Opus 5.5 등)은 LLMFactory 가 with_structured_output 을 json_schema 로 보낸다.
이 방식은 OpenAI strict 와 같이 자유 키 dict(additionalProperties 가 스키마)를
허용하지 않으므로 — 위키 structured-output-strict-schema 참고 — 호출 지점의
스키마를 정적으로 전수 검사한다.

검사 대상: src 의 ``with_structured_output(<Name>)`` 첫 인자가 이름(Name)인 호출.
변수·속성으로 넘기는 호출은 정적으로 해석할 수 없어 대상에서 빠진다(목록으로 남김).
"""
import ast
import importlib
from pathlib import Path

from pydantic import BaseModel

_SRC = Path(__file__).resolve().parents[2] / "src"


def _call_sites() -> list[tuple[str, str, int]]:
    """(모듈 경로, 스키마 이름, 줄 번호)."""
    sites = []
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "with_structured_output"):
                continue
            if node.args and isinstance(node.args[0], ast.Name):
                module = ".".join(path.relative_to(_SRC.parent).with_suffix("").parts)
                sites.append((module, node.args[0].id, node.lineno))
    return sites


def _free_key_dict_paths(schema: dict, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(schema, dict):
        if isinstance(schema.get("additionalProperties"), dict):
            found.append(path)
        for key, value in schema.items():
            found.extend(_free_key_dict_paths(value, f"{path}.{key}"))
    elif isinstance(schema, list):
        for i, value in enumerate(schema):
            found.extend(_free_key_dict_paths(value, f"{path}[{i}]"))
    return found


def _resolve(module: str, name: str):
    obj = getattr(importlib.import_module(module), name, None)
    return obj if isinstance(obj, type) and issubclass(obj, BaseModel) else None


def test_structured_output_schemas_have_no_free_key_dict():
    violations = []
    for module, name, line in _call_sites():
        model = _resolve(module, name)
        if model is None:
            continue
        schema = model.model_json_schema()
        if schema.get("type") != "object":
            violations.append(f"{module}:{line} {name} — 루트가 object 아님")
        for path in _free_key_dict_paths(schema):
            violations.append(f"{module}:{line} {name} — 자유 키 dict {path}")
    assert violations == [], "\n".join(violations)


def test_scan_finds_core_schemas():
    # 정적 해석이 실제로 동작하는지 — 수퍼바이저 결정 스키마는 반드시 잡혀야 한다
    resolved = {name for module, name, _ in _call_sites() if _resolve(module, name)}
    assert "SupervisorDecision" in resolved
    assert len(resolved) >= 10
