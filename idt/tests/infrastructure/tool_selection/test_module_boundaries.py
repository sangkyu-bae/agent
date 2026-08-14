"""tool-recommender — 탈부착·레이어 경계 테스트 (Design §9.3, Plan §4.1).

Plan 성공 기준 "탈부착 검증"을 CI에서 자동으로 지킨다. 사람이 규율로 지키는
규칙은 언젠가 깨지므로, 깨지는 순간 빨간불이 켜지게 만든다.
"""
import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[3] / "src"
_DOMAIN = _SRC / "domain" / "tool_selection"
_INFRA = _SRC / "infrastructure" / "tool_selection"
_ADAPTERS = _INFRA / "adapters"

_STDLIB_OK = {
    "abc", "collections", "collections.abc", "dataclasses", "enum",
    "hashlib", "re", "json", "time", "asyncio", "typing", "__future__",
}


def _module_names(path: Path) -> list[str]:
    """파일이 import 하는 모듈 경로 목록 (문자열 리터럴·주석 제외)."""
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


# ── 도메인 순수성 ────────────────────────────────────────────────────────────


def test_domain_package_exists():
    assert _DOMAIN.is_dir()


@pytest.mark.parametrize("path", _py_files(_DOMAIN), ids=lambda p: p.name)
def test_domain_imports_only_stdlib_and_own_package(path: Path):
    """domain은 표준 라이브러리와 자기 패키지 외 아무것도 참조하지 않는다."""
    for module in _module_names(path):
        root = module.split(".")[0]
        assert module.startswith("src.domain.tool_selection") or root in _STDLIB_OK, (
            f"{path.name} imports {module!r} — domain 순수성 위반 (Design §9.3)"
        )


@pytest.mark.parametrize("path", _py_files(_DOMAIN), ids=lambda p: p.name)
def test_domain_never_imports_infrastructure(path: Path):
    """CLAUDE.md §6 — domain → infrastructure 참조 금지."""
    for module in _module_names(path):
        assert "infrastructure" not in module, f"{path.name} → {module}"


@pytest.mark.parametrize("path", _py_files(_DOMAIN), ids=lambda p: p.name)
def test_domain_never_imports_langchain(path: Path):
    for module in _module_names(path):
        assert not module.startswith("langchain"), f"{path.name} → {module}"


# ── 코어의 프레임워크 무지 (§1.2) ────────────────────────────────────────────


def _core_files() -> list[Path]:
    """adapters/ 를 제외한 infrastructure 코어 파일."""
    return [p for p in _py_files(_INFRA) if _ADAPTERS not in p.parents]


@pytest.mark.parametrize("path", _core_files(), ids=lambda p: p.name)
def test_infra_core_never_imports_langchain(path: Path):
    """langchain 참조는 adapters/ 안에만 존재한다 (MiddlewareBuilder 선례)."""
    for module in _module_names(path):
        assert not module.startswith("langchain"), (
            f"{path.name} imports {module!r} — langchain은 adapters/ 전용 (Design §9.3)"
        )


@pytest.mark.parametrize("path", _py_files(_INFRA), ids=lambda p: p.name)
def test_infra_never_imports_application_or_interfaces(path: Path):
    for module in _module_names(path):
        assert not module.startswith("src.application"), f"{path.name} → {module}"
        assert not module.startswith("src.interfaces"), f"{path.name} → {module}"


def test_adapters_do_import_langchain():
    """어댑터는 langchain을 알아야 한다 — 격리가 성립하려면 한쪽엔 있어야 한다."""
    modules = [m for p in _py_files(_ADAPTERS) for m in _module_names(p)]
    assert any(m.startswith("langchain") for m in modules)


# ── 탈부착 (§1.1-2, Plan §4.1) ───────────────────────────────────────────────


_DECLARED_CONSUMERS = {"api\\main.py", "api/main.py"}
"""tool_selection을 import 해도 되는 **선언된** 결선 지점 (module-4).

의도적으로 좁게 유지한다. 여기 없는 파일이 모듈을 import 하면 탈부착 계약이
소리 없이 무너지므로 테스트가 실패해야 한다.

`general_chat/use_case.py`는 여기 없다 — 결선을 duck typing(`tool_filter`)으로
받아 tool_selection을 **import 하지 않기** 때문이다. 그래서 모듈을 지워도
application 계층은 그대로 동작한다.
"""


def test_only_declared_consumers_depend_on_it():
    """모듈 밖에서 tool_selection을 import 하는 곳은 선언된 결선 지점뿐이다.

    이게 성립하는 한 두 디렉토리를 지웠을 때 고쳐야 할 곳이 정확히 이 목록이다.
    """
    offenders = []
    for path in _py_files(_SRC):
        if _DOMAIN in path.parents or _INFRA in path.parents:
            continue
        rel = str(path.relative_to(_SRC))
        if rel in _DECLARED_CONSUMERS:
            continue
        if any("tool_selection" in m for m in _module_names(path)):
            offenders.append(rel)
    assert offenders == [], f"선언되지 않은 소비자: {offenders}"


def test_application_layer_never_imports_the_module():
    """application은 duck typing으로만 결선한다 — 모듈 제거 시 무영향.

    `GeneralChatUseCase`가 `LangChainToolFilter`를 직접 import 하는 순간
    "디렉토리 삭제 = 기능 제거"가 깨지고 import 에러가 난다.
    """
    app_dir = _SRC / "application"
    offenders = [
        str(p.relative_to(_SRC))
        for p in _py_files(app_dir)
        if any("tool_selection" in m for m in _module_names(p))
    ]
    assert offenders == [], f"application이 모듈을 직접 참조: {offenders}"


def test_wiring_is_actually_present():
    """결선이 조용히 사라지지 않았는지 확인 (역방향 가드).

    위 두 테스트는 '너무 많이 붙는 것'을 막는다. 이 테스트는 '붙어 있어야 할
    것이 빠지는 것'을 막는다.
    """
    main_py = (_SRC / "api" / "main.py").read_text(encoding="utf-8")
    assert "tool_filter=_build_tool_filter()" in main_py
    assert "settings.tool_selector_enabled" in main_py


def test_infra_depends_only_on_declared_domain_ports():
    """infrastructure가 참조하는 도메인은 선언된 것뿐이다 (의존 확산 감시)."""
    allowed_roots = {
        "src.domain.tool_selection",
        "src.domain.llm.interfaces",
        "src.domain.llm_model.entity",
        "src.domain.logging.interfaces.logger_interface",
    }
    for path in _py_files(_INFRA):
        for module in _module_names(path):
            if not module.startswith("src.domain"):
                continue
            assert any(module.startswith(root) for root in allowed_roots), (
                f"{path.name} imports {module!r} — 선언되지 않은 도메인 의존"
            )
