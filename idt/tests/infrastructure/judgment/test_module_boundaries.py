"""judgment-backend — 레이어 경계 AST 테스트 (Design §9.2, 테스트 8.3 #12).

prompt_guard 의 같은 테스트를 복제했다
(위키: detachable-module-seam §4, ast-source-contract-tests).
domain 은 stdlib 만, infrastructure/judgment 는 application 을 모르며,
judgment 패키지를 import 하는 외부 파일은 `_DECLARED_CONSUMERS` 뿐이다.
"""

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[3] / "src"
_DOMAIN = _SRC / "domain" / "judgment"
_INFRA = _SRC / "infrastructure" / "judgment"

_STDLIB_OK = {
    "__future__",
    "abc",
    "asyncio",
    "collections",
    "collections.abc",
    "dataclasses",
    "enum",
    "hashlib",
    "math",
    "time",
    "types",
    "typing",
}
_FORBIDDEN_IN_DOMAIN = ("langchain", "pydantic", "openai", "httpx", "typesafe_sdk")

# Design §9.2 — judgment 패키지를 물어도 되는 외부 파일 전수 목록.
# 늘릴 때는 근거 주석과 함께 (위키 detachable-module-seam §4b).
_DECLARED_CONSUMERS = {
    # module-4: 조립 1곳
    "src/api/main.py",
    # module-4: 첫 소비 지점 — 포트만 의존(구현 직접 참조 금지는 아래 별도 테스트)
    "src/infrastructure/search_decision/judgment_adapter.py",
}


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
        lambda n: n not in _STDLIB_OK and not n.startswith("src.domain.judgment"),
    )
    assert bad == [], f"domain/judgment 외부 의존: {bad}"


def test_domain_never_imports_frameworks_or_sdks():
    bad = _offenders(_DOMAIN, lambda n: n.startswith(_FORBIDDEN_IN_DOMAIN))
    assert bad == [], bad


def test_infrastructure_does_not_import_application_or_api():
    if not _INFRA.exists():
        pytest.skip("infrastructure/judgment 는 module-2 에서 생성된다")
    bad = _offenders(_INFRA, lambda n: n.startswith(("src.application", "src.api")))
    assert bad == [], bad


def test_only_declared_consumers_import_judgment_package():
    consumers = []
    for path in _py_files(_SRC):
        rel = path.relative_to(_SRC.parent).as_posix()
        if rel.startswith(("src/domain/judgment/", "src/infrastructure/judgment/")):
            continue
        if any(
            n.startswith(("src.domain.judgment", "src.infrastructure.judgment"))
            for n in _imports(path)
        ):
            consumers.append(rel)
    undeclared = sorted(set(consumers) - _DECLARED_CONSUMERS)
    assert undeclared == [], f"judgment 미선언 소비자: {undeclared}"


def test_search_decision_adapter_depends_on_port_only():
    """소비 지점은 domain 포트만 — infrastructure/judgment 구현 직접 참조 금지(§9.3)."""
    adapter = _SRC / "infrastructure" / "search_decision" / "judgment_adapter.py"
    if not adapter.exists():
        pytest.skip("judgment_adapter.py 는 module-4 에서 생성된다")
    bad = [n for n in _imports(adapter) if n.startswith("src.infrastructure.judgment")]
    assert bad == [], bad
