"""market_analysis 격리 계약 — stock-analysis-agents
design §14.2, Plan NFR "분리 가능성" · SC-8.

I1  코어 소스는 market_analysis 를 import 하지 않는다 (떼어낼 수 있다)
I2  main.py 는 조립 파일(market_analysis_di)만 안다
I3  domain 은 표준 라이브러리만
I4  application 은 domain/market_analysis·표준
라이브러리·pydantic 만 (다른 기능·인프라·웹 금지)
I5  infrastructure 는 자기 application·api·fastapi
를 모른다 (포트는 Protocol, 구조적 타이핑).
    플랫폼 application import 는 adapters/ 에서만 (v0.3)
I6  기본값은 꺼짐이다

문자열 검색은 독스트링에 오탐하므로 AST 로 본다 (firewall_admin 격리 계약과 같은 방식).
"""

import ast
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
_PKG = "market_analysis"
_OWNED = {
    "api/market_analysis_di.py",
    "api/routes/market_analysis_router.py",
}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
            found.extend(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
    return found


def _is_module_file(rel: str) -> bool:
    return f"/{_PKG}/" in f"/{rel}" or rel in _OWNED


def test_i1_core_does_not_import_market_analysis():
    offenders = []
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_SRC).as_posix()
        if _is_module_file(rel) or rel == "api/main.py":
            continue
        for mod in _imports(path):
            if _PKG in mod.split(".") or mod.endswith("market_analysis_router"):
                offenders.append(f"{rel} -> {mod}")
    assert offenders == [], offenders


def test_i2_main_only_knows_the_di_module():
    mods = [m for m in _imports(_SRC / "api" / "main.py") if _PKG in m]
    assert mods, "main.py 가 market_analysis_di 를 배선하지 않는다"
    assert all(m.startswith("src.api.market_analysis_di") for m in mods), mods


def _layer_imports(layer: str) -> list[tuple[str, str]]:
    out = []
    for path in (_SRC / layer / _PKG).rglob("*.py"):
        rel = path.relative_to(_SRC).as_posix()
        out.extend((rel, mod) for mod in _imports(path))
    return out


def test_i3_domain_uses_stdlib_and_own_package_only():
    offenders = []
    for rel, mod in _layer_imports("domain"):
        if mod.startswith(f"src.domain.{_PKG}") or mod == "__future__":
            continue
        if mod.split(".")[0] in sys.stdlib_module_names:
            continue
        offenders.append(f"{rel} -> {mod}")
    assert offenders == [], offenders


def test_i4_application_uses_only_its_domain():
    offenders = []
    for rel, mod in _layer_imports("application"):
        top = mod.split(".")[0]
        if mod.startswith(f"src.domain.{_PKG}") or mod.startswith(
            f"src.application.{_PKG}"
        ):
            continue
        # 로거 포트(LoggerInterface)는 모든 모듈이 공유하는 도메인 인터페이스라 허용한다
        if mod.startswith("src.domain.logging"):
            continue
        if top in sys.stdlib_module_names or top in ("pydantic", "__future__"):
            continue
        offenders.append(f"{rel} -> {mod}")
    assert offenders == [], offenders


def test_i5_infrastructure_does_not_import_application_or_web():
    """v0.3 (module-3): 자기 모듈 application
    은 금지. 플랫폼 application 은 adapters/ 에서만.

    어댑터는 플랫폼 RunAgentRequest(application) 같은 것을 써야 포트를 구현할 수 있다.
    """
    offenders = []
    for rel, mod in _layer_imports("infrastructure"):
        in_adapters = rel.startswith("infrastructure/market_analysis/adapters/")
        if mod.startswith(f"src.application.{_PKG}"):
            offenders.append(f"{rel} -> {mod}")
        elif mod.startswith("src.application") and not in_adapters:
            offenders.append(f"{rel} -> {mod}")
        elif mod.startswith("src.api") or mod.split(".")[0] == "fastapi":
            offenders.append(f"{rel} -> {mod}")
    assert offenders == [], offenders


def test_i6_defaults_are_off():
    tree = ast.parse((_SRC / "config.py").read_text(encoding="utf-8"))
    defaults = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id.startswith("market_analysis_")
            and isinstance(node.value, ast.Constant)
        ):
            defaults[node.target.id] = node.value.value
    assert defaults == {
        "market_analysis_enabled": False,
        "market_analysis_ticker_enabled": True,  # 모듈이 켜졌을 때만 의미가 있다
    }
