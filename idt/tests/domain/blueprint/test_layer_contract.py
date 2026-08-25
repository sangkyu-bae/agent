"""AST 계약 (위키 ast-source-contract-tests): domain/blueprint 는 순수 Python."""

import ast
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[3] / "src" / "domain" / "blueprint"
FORBIDDEN_ROOTS = {
    "fitz",
    "pymupdf",
    "pptx",
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


def test_domain_blueprint_has_no_external_or_outer_layer_imports():
    files = list(DOMAIN.glob("*.py"))
    assert files, "domain/blueprint 파일 없음"
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


def test_expected_modules_exist():
    names = {f.name for f in DOMAIN.glob("*.py")}
    for required in (
        "value_objects.py",
        "schemas.py",
        "policies.py",
        "interfaces.py",
        "errors.py",
        "tool_config.py",
    ):
        assert required in names, required


# ── blueprint-font-mapping-migration §8.5 — 로드 경계 누락 방지 (DR-1) ──────

SRC = Path(__file__).resolve().parents[3] / "src"
_LOADER = "blueprint_from_dict"
_NORMALIZER = "normalize_blueprint_fonts"


def _names(path: Path) -> set[str]:
    """모듈이 참조하는 이름 — 임포트명 + 호출명."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.Name):
            found.add(node.id)
    return found


def test_every_blueprint_loader_call_site_normalizes_fonts():
    """Option C 의 유일한 약점 방어 — 새 로드 경로가 정규화를 빠뜨리면 실패한다.

    font_normalization 자신과 serialization(정의처)은 예외.
    """
    exempt = {"font_normalization.py", "serialization.py"}
    offenders = []
    for f in SRC.rglob("*.py"):
        if f.name in exempt:
            continue
        names = _names(f)
        if _LOADER in names and _NORMALIZER not in names:
            offenders.append(str(f.relative_to(SRC)))
    assert not offenders, f"정규화를 거치지 않는 로드 경로: {offenders}"


def test_font_normalization_module_exists_in_domain():
    assert (DOMAIN / "font_normalization.py").exists()
