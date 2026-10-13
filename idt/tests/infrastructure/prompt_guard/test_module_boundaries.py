"""prompt-guard — 레이어 경계 AST 테스트 (Design §9.2, 테스트 8.3 #15).

사람이 규율로 지키는 "domain 은 stdlib 만, application 은 infrastructure 를 모른다"를
CI 에서 빨간불로 만든다 (위키: ast-source-contract-tests).
"""
import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[3] / "src"
_DOMAIN = _SRC / "domain" / "prompt_guard"
_APP = _SRC / "application" / "prompt_guard"
_INFRA = _SRC / "infrastructure" / "prompt_guard"
_USE_CASES = (
    _SRC / "application" / "agent_builder" / "run_agent_use_case.py",
    _SRC / "application" / "general_chat" / "use_case.py",
)

_STDLIB_OK = {
    "__future__", "abc", "asyncio", "collections", "collections.abc",
    "dataclasses", "enum", "hashlib", "re", "time", "typing", "unicodedata",
}
_FORBIDDEN_IN_DOMAIN = ("langchain", "pydantic", "openai")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _offenders(root: Path, is_bad) -> list[tuple[str, str]]:
    return [
        (path.name, name)
        for path in _py_files(root)
        for name in _imports(path)
        if is_bad(name)
    ]


def test_domain_imports_only_stdlib_and_domain():
    bad = _offenders(
        _DOMAIN,
        lambda n: n not in _STDLIB_OK and not n.startswith("src.domain."),
    )
    assert bad == [], f"domain/prompt_guard 외부 의존: {bad}"


def test_domain_never_imports_langchain_or_pydantic():
    bad = _offenders(_DOMAIN, lambda n: n.startswith(_FORBIDDEN_IN_DOMAIN))
    assert bad == [], bad


def test_application_does_not_import_infrastructure():
    bad = _offenders(_APP, lambda n: n.startswith("src.infrastructure"))
    assert bad == [], bad


def test_use_cases_depend_only_on_prompt_guard_domain():
    """두 유스케이스는 Port·정책·상수(domain)만 안다 — 구현 직접 참조 금지."""
    for uc in _USE_CASES:
        # Check G-8: 구현(infrastructure)뿐 아니라 서비스(application)도 직접 참조
        # 금지 —
        # 유스케이스는 Port 로만 의존해야 DI 에서 None 으로 떼어낼 수 있다 (§9.2).
        bad = [
            n for n in _imports(uc)
            if n.startswith(
                ("src.infrastructure.prompt_guard", "src.application.prompt_guard")
            )
        ]
        assert bad == [], (uc.name, bad)


def test_infrastructure_depends_on_domain_not_application_guard():
    """infrastructure/prompt_guard 는 domain·llm_model 공급자만 안다.

    module-2 전에는 디렉터리가 없어 skip 된다.
    """
    if not _INFRA.exists():
        pytest.skip("infrastructure/prompt_guard 는 module-2 에서 생성된다")
    bad = _offenders(
        _INFRA,
        lambda n: n.startswith(
            ("src.application.prompt_guard", "src.application.agent_builder")
        ),
    )
    assert bad == [], bad
