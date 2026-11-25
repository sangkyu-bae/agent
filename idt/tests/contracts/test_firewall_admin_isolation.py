"""firewall-admin-console 격리 계약 (Design §9.3, §8.2 #21).

I1  코어 소스는 firewall_admin 패키지를 import 하지 않는다 (모듈을 떼어낼 수 있다)
I2  main.py 는 조립 파일(firewall_admin_di)만 안다
I3  레이어 방향: domain 은 표준 라이브러리만, infrastructure 는 application 을 모른다
I4  기본값은 꺼짐이다

문자열 검색은 독스트링에 오탐하므로 AST 로 본다.
"""
import ast
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
_PKG = "firewall_admin"
# 이 모듈을 import 해도 되는 파일 — 모듈 자신과 조립·표현 계층
_OWNED = {
    "api/firewall_admin_di.py",
    "api/routes/admin_firewall_router.py",
    "interfaces/schemas/firewall_admin.py",
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


def test_I1_core_does_not_import_firewall_admin():
    offenders = []
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_SRC).as_posix()
        if _is_module_file(rel) or rel == "api/main.py":
            continue
        for mod in _imports(path):
            if _PKG in mod.split(".") or mod.endswith("admin_firewall_router"):
                offenders.append(f"{rel} -> {mod}")
    assert offenders == [], offenders


def test_I2_main_only_knows_the_di_module():
    mods = [m for m in _imports(_SRC / "api" / "main.py") if "firewall" in m]
    assert mods, "main.py 가 firewall_admin_di 를 배선하지 않는다"
    assert all(m.startswith("src.api.firewall_admin_di") for m in mods), mods


def _layer_imports(layer: str) -> list[tuple[str, str]]:
    out = []
    for path in (_SRC / layer / _PKG).rglob("*.py"):
        rel = path.relative_to(_SRC).as_posix()
        out.extend((rel, mod) for mod in _imports(path))
    return out


def test_I3_domain_uses_stdlib_and_own_package_only():
    offenders = []
    for rel, mod in _layer_imports("domain"):
        top = mod.split(".")[0]
        if mod.startswith(f"src.domain.{_PKG}") or mod == "__future__":
            continue
        if top in sys.stdlib_module_names:
            continue
        offenders.append(f"{rel} -> {mod}")
    assert offenders == [], offenders


def test_I3_application_does_not_import_infrastructure_or_web():
    offenders = [
        f"{rel} -> {mod}" for rel, mod in _layer_imports("application")
        if mod.startswith("src.infrastructure") or mod.split(".")[0] in ("fastapi", "httpx")
    ]
    assert offenders == [], offenders


def test_I3_infrastructure_does_not_import_application_or_web():
    offenders = [
        f"{rel} -> {mod}" for rel, mod in _layer_imports("infrastructure")
        if mod.startswith("src.application") or mod.startswith("src.api")
        or mod.split(".")[0] == "fastapi"
    ]
    assert offenders == [], offenders


def test_I4_default_is_off_and_tokens_empty():
    tree = ast.parse((_SRC / "config.py").read_text(encoding="utf-8"))
    defaults = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
                and node.target.id.startswith("firewall_admin_")
                and isinstance(node.value, ast.Constant)):
            defaults[node.target.id] = node.value.value
    assert defaults["firewall_admin_enabled"] is False
    assert defaults["firewall_admin_fwctl_token"] == ""
    assert defaults["firewall_admin_grafana_token"] == ""
    assert set(defaults) == {
        "firewall_admin_enabled", "firewall_admin_fwctl_url", "firewall_admin_fwctl_token",
        "firewall_admin_grafana_url", "firewall_admin_grafana_token",
        "firewall_admin_agent_id",  # firewall-agent design §4.4 — 기본 "" (미설정)
    }
    assert defaults["firewall_admin_agent_id"] == ""
