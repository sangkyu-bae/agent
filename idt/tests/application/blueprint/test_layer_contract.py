"""AST 계약: application/blueprint 은 infrastructure/api/interfaces 임포트 금지."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[3] / "src" / "application" / "blueprint"
FORBIDDEN_PREFIXES = ("src.infrastructure", "src.api", "src.interfaces")
FORBIDDEN_ROOTS = {"fitz", "pymupdf", "pptx", "sqlalchemy", "fastapi", "langchain"}


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_application_blueprint_imports_only_domain_and_stdlib():
    files = list(APP.glob("*.py"))
    assert files
    for f in files:
        for mod in _imports(f):
            assert not mod.startswith(FORBIDDEN_PREFIXES), f"{f.name}: {mod}"
            assert mod.split(".")[0] not in FORBIDDEN_ROOTS, f"{f.name}: {mod}"
