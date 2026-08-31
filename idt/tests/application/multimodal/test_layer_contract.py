"""AST 계약 (위키 ast-source-contract-tests) — application/multimodal.

1) fitz/langchain/sqlalchemy 등 구체 라이브러리 import 0
2) UseCase 가 포트 객체에 대해 Protocol 에 선언되지 않은 메서드를 호출하지 않는다
   (구현 교체 시 AttributeError 를 아무도 못 잡는 문제 차단).
"""

import ast
from pathlib import Path

from src.domain.multimodal.interfaces import (
    ImageExtractorPort,
    MultimodalSettingRepository,
    VisionDescriberPort,
)

APP = Path(__file__).resolve().parents[3] / "src" / "application" / "multimodal"
FORBIDDEN_ROOTS = {
    "fitz",
    "pymupdf",
    "langchain",
    "langchain_core",
    "sqlalchemy",
    "fastapi",
}

# 포트 속성명 → 허용 메서드/속성 (Protocol 선언 + dataclass 필드)
PORT_SURFACE = {
    "_settings_repo": {"get", "update"},
    "_adapters": {"build", "register", "supported"},  # 레지스트리(application 내부)
    "_extractors": {"resolve", "register", "supported"},
}
EXTRACTOR_SURFACE = {"extract", "supported_extensions"}
ADAPTER_SURFACE = {"describe", "provider"}


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_application_multimodal_has_no_concrete_library_imports():
    files = list(APP.glob("*.py"))
    assert files
    for f in files:
        for mod in _imports(f):
            assert mod.split(".")[0] not in FORBIDDEN_ROOTS, f"{f.name}: {mod}"
            assert not mod.startswith(("src.api", "src.interfaces")), f"{f.name}: {mod}"


def _attr_calls_on(tree: ast.AST, base_name: str) -> set[str]:
    """self.<base_name>.<attr>(...) 및 <base_name>.<attr>(...) 형태의 attr 수집."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        v = node.value
        if (
            isinstance(v, ast.Attribute)
            and isinstance(v.value, ast.Name)
            and v.value.id == "self"
        ):
            if v.attr == base_name:
                found.add(node.attr)
        elif isinstance(v, ast.Name) and v.id == base_name:
            found.add(node.attr)
    return found


def test_use_cases_only_call_declared_port_members():
    for fname in ("use_case.py", "settings_use_case.py"):
        tree = ast.parse((APP / fname).read_text(encoding="utf-8"))
        for attr, allowed in PORT_SURFACE.items():
            used = _attr_calls_on(tree, attr)
            assert used <= allowed, f"{fname}: {attr} uses undeclared {used - allowed}"
        assert _attr_calls_on(tree, "extractor") <= EXTRACTOR_SURFACE
        assert _attr_calls_on(tree, "adapter") <= ADAPTER_SURFACE


def test_protocols_declare_expected_surface():
    """PORT_SURFACE 상수가 실제 Protocol 과 어긋나면 이 테스트가 먼저 깨진다."""
    assert {"get", "update"} <= set(MultimodalSettingRepository.__protocol_attrs__)
    assert {"extract", "supported_extensions"} <= set(
        ImageExtractorPort.__protocol_attrs__
    )
    assert {"describe", "provider"} <= set(VisionDescriberPort.__protocol_attrs__)
