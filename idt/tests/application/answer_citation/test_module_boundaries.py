"""answer-citation-verification — 탈착 경계 AST 테스트 (Design §9.2·§9.3, U11).

기능을 뺄 때 고칠 곳을 이 테스트가 전수 열거한다([[detachable-module-seam]]).
기존 코드(검색 도구·도구 팩토리·답변 노드·근거 칩 서비스)는 answer_citation 을
import 하지 않고 duck typing(citation_labeler / citation_service /
citation_enricher)으로만 받는다.
판정 포트(domain/hallucination)는 인용 모듈을 모른다
— 인용 VO 는 citation_check.py 에 둔다.
"""

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
_PACKAGE_DIRS = (
    _SRC / "domain" / "answer_citation",
    _SRC / "application" / "answer_citation",
    _SRC / "infrastructure" / "answer_citation",
)
_PREFIXES = (
    "src.domain.answer_citation",
    "src.application.answer_citation",
    "src.infrastructure.answer_citation",
)
# 패키지 밖에서 answer_citation 을 import 하는 파일 — 조립 모듈 하나뿐이다.
_DECLARED_CONSUMERS = {"api/answer_citation_di.py"}
_DI_MODULE = "src.api.answer_citation_di"
_DI_CONSUMERS = {"api/main.py"}
_DOMAIN_ALLOWED = (
    "src.domain.answer_citation",
    "src.domain.hallucination.citation_check",
    "src.domain.hallucination.grounding_edit",
)
_STDLIB_OK = {
    "__future__",
    "abc",
    "collections",
    "collections.abc",
    "dataclasses",
    "re",
    "typing",
    "unicodedata",
}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(p: Path) -> str:
    return p.relative_to(_SRC).as_posix()


def _inside(p: Path) -> bool:
    return any(d in p.parents for d in _PACKAGE_DIRS)


def test_only_di_module_imports_answer_citation():
    users = {
        _rel(p)
        for p in _py_files(_SRC)
        if not _inside(p) and any(n.startswith(_PREFIXES) for n in _imports(p))
    }
    assert users == _DECLARED_CONSUMERS


def test_only_main_imports_di_module():
    users = {
        _rel(p)
        for p in _py_files(_SRC)
        if p.name != "answer_citation_di.py" and _DI_MODULE in _imports(p)
    }
    assert users == _DI_CONSUMERS


def test_domain_depends_only_on_stdlib_and_allowed_domain():
    bad = [
        (p.name, n)
        for p in _py_files(_SRC / "domain" / "answer_citation")
        for n in _imports(p)
        if n not in _STDLIB_OK and not n.startswith(_DOMAIN_ALLOWED)
    ]
    assert bad == []


def test_hallucination_domain_does_not_know_answer_citation():
    users = [
        p.name
        for p in _py_files(_SRC / "domain" / "hallucination")
        if any(n.startswith(_PREFIXES) for n in _imports(p))
    ]
    assert users == []
