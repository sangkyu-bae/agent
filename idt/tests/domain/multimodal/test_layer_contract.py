"""AST 계약 (위키 ast-source-contract-tests): domain/multimodal 은 순수 Python."""

import ast
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[3] / "src" / "domain" / "multimodal"
FORBIDDEN_ROOTS = {
    "fitz",
    "pymupdf",
    "langchain",
    "langchain_core",
    "langchain_openai",
    "langchain_anthropic",
    "sqlalchemy",
    "openai",
    "anthropic",
    "fastapi",
}
FORBIDDEN_PREFIXES = (
    "src.infrastructure",
    "src.application",
    "src.api",
    "src.interfaces",
)


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_domain_multimodal_has_no_external_or_outer_layer_imports():
    files = list(DOMAIN.glob("*.py"))
    assert files, "domain/multimodal 파일 없음"
    for f in files:
        for mod in _imports(f):
            assert mod.split(".")[0] not in FORBIDDEN_ROOTS, f"{f.name}: {mod}"
            assert not mod.startswith(FORBIDDEN_PREFIXES), f"{f.name}: {mod}"


def test_pydantic_only_in_schemas():
    for f in DOMAIN.glob("*.py"):
        if f.name == "schemas.py":
            continue
        roots = {m.split(".")[0] for m in _imports(f)}
        assert "pydantic" not in roots, f.name
