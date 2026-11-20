"""source-passage-viewer — 탈착 경계 AST 테스트 (Design §9.2, §8.2 #15·#16).

기능을 뺄 때 고쳐야 할 곳을 사람의 기억이 아니라 이 테스트가 전수 열거한다
([[detachable-module-seam]] §4b). 기존 코드는 source_viewer 를 import 하지 않고
duck typing(`original_sink`, `viewer_enricher`)으로만 받는다.
"""
import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
_DOMAIN = _SRC / "domain" / "source_viewer"
_APP = _SRC / "application" / "source_viewer"
_PACKAGE_DIRS = (
    _DOMAIN,
    _APP,
    _SRC / "infrastructure" / "source_viewer",
)
_PACKAGE_PREFIXES = (
    "src.domain.source_viewer",
    "src.application.source_viewer",
    "src.infrastructure.source_viewer",
)
# Design §11.2 — source_viewer 를 import 하는 패키지 밖 파일. 조립(di)과 라우터뿐이다.
# 소비자를 늘리려면 여기에 근거와 함께 추가하고 Design §11.2 표도 같이 고친다.
_DECLARED_CONSUMERS = {
    "api/source_viewer_di.py",
    "api/routes/source_viewer_router.py",
}
# 조립 모듈을 부르는 곳은 main.py 하나 — 기능 제거 시 import·wire 호출·주입 4곳만 지운다.
_DI_MODULE = "src.api.source_viewer_di"
_DI_CONSUMERS = {"api/main.py"}

_STDLIB_OK = {
    "__future__", "abc", "dataclasses", "enum", "re", "typing",
}
_DOMAIN_ALLOWED = ("src.domain.source_viewer", "src.domain.agent_run.entities")


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


def _inside_package(path: Path) -> bool:
    return any(d in path.parents for d in _PACKAGE_DIRS)


def test_domain_imports_only_stdlib_and_allowed_domain():
    bad = [
        (p.name, n)
        for p in _py_files(_DOMAIN)
        for n in _imports(p)
        if n not in _STDLIB_OK and not n.startswith(_DOMAIN_ALLOWED)
    ]
    assert bad == [], f"domain/source_viewer 외부 의존: {bad}"


def test_application_does_not_import_infrastructure():
    bad = [
        (p.name, n)
        for p in _py_files(_APP)
        for n in _imports(p)
        if n.startswith("src.infrastructure")
    ]
    assert bad == [], bad


def _importers_of(prefixes: tuple[str, ...]) -> set[str]:
    return {
        p.relative_to(_SRC).as_posix()
        for p in _py_files(_SRC)
        if not _inside_package(p)
        and any(n.startswith(prefixes) for n in _imports(p))
    }


def test_source_viewer_consumers_match_declaration_exactly():
    """패키지 밖 소비자 = 선언 목록. 늘어도 줄어도 실패한다 (Design §12 M5)."""
    assert _importers_of(_PACKAGE_PREFIXES) == _DECLARED_CONSUMERS, (
        "source_viewer 소비자가 선언과 다르다 — duck typing 으로 받거나 "
        "_DECLARED_CONSUMERS·Design §11.2 를 함께 고칠 것"
    )


def test_only_main_imports_di_module():
    assert _importers_of((_DI_MODULE,)) - {"api/source_viewer_di.py"} == _DI_CONSUMERS
