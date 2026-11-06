"""관리자 도구 권한 DI 배선 테스트.

Design Ref: tool-access-control §9.1 — main.py 단일 DI 집중.
- 팩토리가 실제 저장소 클래스를 같은 요청 세션 하나로 묶는지 (DB-001)
- 라우터 플레이스홀더가 앱에서 override 되고 라우트가 등록됐는지 (미배선 시 500 NotImplementedError)
"""
from unittest.mock import MagicMock

from src.api.main import app, create_tool_access_factories
from src.api.routes.admin_tool_access_router import (
    get_default_tool_access_use_case,
    get_department_tool_access_use_case,
    get_user_tool_access_use_case,
)
from src.application.tool_access.admin_use_cases import (
    DefaultToolAccessUseCase,
    DepartmentToolAccessUseCase,
    UserToolAccessUseCase,
)
from src.infrastructure.auth.user_repository import UserRepository
from src.infrastructure.department.department_repository import DepartmentRepository
from src.infrastructure.tool_access.repository import ToolAccessRepository
from src.infrastructure.tool_catalog.tool_catalog_repository import ToolCatalogRepository


def _repos(uc) -> dict[str, object]:
    return {k: v for k, v in vars(uc).items() if hasattr(v, "_session")}


def test_factories_build_real_repositories_on_one_session():
    default_f, dept_f, user_f = create_tool_access_factories()
    session = MagicMock()

    default_uc = default_f(session=session)
    dept_uc = dept_f(session=session)
    user_uc = user_f(session=session)

    assert isinstance(default_uc, DefaultToolAccessUseCase)
    assert isinstance(dept_uc, DepartmentToolAccessUseCase)
    assert isinstance(user_uc, UserToolAccessUseCase)

    assert isinstance(user_uc._grants, ToolAccessRepository)
    assert isinstance(user_uc._catalog, ToolCatalogRepository)
    assert isinstance(user_uc._users, UserRepository)
    assert isinstance(user_uc._departments, DepartmentRepository)
    assert isinstance(dept_uc._departments, DepartmentRepository)

    for uc in (default_uc, dept_uc, user_uc):
        sessions = {id(r._session) for r in _repos(uc).values()}
        assert sessions == {id(session)}


def test_placeholders_are_overridden_in_app():
    for dep in (
        get_default_tool_access_use_case,
        get_department_tool_access_use_case,
        get_user_tool_access_use_case,
    ):
        assert dep in app.dependency_overrides


def _resolver_of(uc):
    from src.application.tool_access.resolver import ToolAccessResolver

    r = getattr(uc, "_tool_access_resolver", None) or getattr(uc, "_access_resolver", None)
    assert isinstance(r, ToolAccessResolver), f"{type(uc).__name__} 에 Resolver 미주입"
    return r


def test_module3_use_cases_get_resolver_on_request_session():
    """module-3: 목록·생성·수정·상세·포크·컴포저 팩토리가 Resolver 를 같은 세션으로 주입."""
    from src.api.routes.agent_builder_router import (
        get_create_agent_use_case,
        get_fork_agent_use_case,
        get_get_agent_use_case,
        get_update_agent_use_case,
    )
    from src.api.routes.agent_composer_router import get_compose_agent_use_case
    from src.api.routes.tool_catalog_router import get_list_tool_catalog_use_case

    for dep in (
        get_list_tool_catalog_use_case,
        get_create_agent_use_case,
        get_update_agent_use_case,
        get_get_agent_use_case,
        get_fork_agent_use_case,
        get_compose_agent_use_case,
    ):
        session = MagicMock()
        uc = app.dependency_overrides[dep](session=session)
        resolver = _resolver_of(uc)
        for repo in (resolver._grant_repo, resolver._user_repo, resolver._department_repo):
            assert repo._session is session


def test_pipeline_use_case_gets_resolver_when_enabled():
    from src.api.routes.agent_pipeline_router import get_agent_pipeline_use_case

    factory = app.dependency_overrides.get(get_agent_pipeline_use_case)
    if factory is None:
        import pytest

        pytest.skip("agent pipeline disabled in this environment")
    uc = factory(session=MagicMock(), compose_uc=MagicMock(), create_uc=MagicMock())
    _resolver_of(uc)


def test_routes_are_registered_in_openapi():
    # 위키 router-map: app.routes 는 _IncludedRouter 로 평탄화되지 않으므로 openapi 로 확인
    paths = app.openapi()["paths"]
    assert "/api/v1/admin/tool-access/default" in paths
    assert "/api/v1/admin/tool-access/departments/{department_id}" in paths
    assert "/api/v1/admin/tool-access/users/{user_id}" in paths
    assert set(paths["/api/v1/admin/tool-access/default"]) == {"get", "put"}


# ── module-4: 실행 시점 판정 배선 ──────────────────────────────────────────────

import ast  # noqa: E402
from pathlib import Path  # noqa: E402

_SRC = Path(__file__).resolve().parents[2] / "src"


def _calls_missing_kw(path: Path, attr: str, kw: str) -> list[int]:
    """`<x>.{attr}(...)` 호출 중 키워드 `kw` 가 빠진 줄 번호 (정의부 제외)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    missing = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == attr
            and not any(k.arg == kw for k in node.keywords)
        ):
            missing.append(node.lineno)
    return missing


def test_every_compile_call_in_run_use_case_passes_tool_access():
    # Design §7: _prepare_graph·_resume_graph 두 지점. 새 호출 지점이 생겨도 빠지지 않게 고정.
    path = _SRC / "application/agent_builder/run_agent_use_case.py"
    calls = [n for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "compile"]
    assert len(calls) >= 2
    assert _calls_missing_kw(path, "compile", "tool_access") == []


def test_compiler_recursion_passes_tool_access():
    path = _SRC / "application/agent_builder/workflow_compiler.py"
    assert _calls_missing_kw(path, "_compile_sub_agent", "tool_access") == []
    # 재귀 self.compile(...) 도 같은 값을 넘긴다
    tree = ast.parse(path.read_text(encoding="utf-8"))
    recursive = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "compile" and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"
    ]
    assert recursive and all(any(k.arg == "tool_access" for k in c.keywords) for c in recursive)


def test_run_use_case_factories_inject_resolver():
    from src.api.routes.agent_builder_router import get_run_agent_use_case
    from src.api.routes.ws_router import get_ws_run_agent_use_case

    for dep in (get_run_agent_use_case, get_ws_run_agent_use_case):
        session = MagicMock()
        uc = app.dependency_overrides[dep](session=session)
        resolver = _resolver_of(uc)
        assert resolver._grant_repo._session is session


def test_approval_executor_has_access_checker():
    from src.api.main import _build_approval_executor
    from src.application.tool_access.checker import SessionScopedToolAccessChecker

    executor = _build_approval_executor(MagicMock())
    assert isinstance(executor._access_checker, SessionScopedToolAccessChecker)


def test_general_chat_construction_injects_resolver():
    """Check G-01: 일반 채팅(REST·WS 공용 팩토리)도 실행자 권한으로 도구를 거른다.

    팩토리는 앱 기동 싱글턴(HybridSearch)이 있어야 호출되므로 main.py 생성 호출부를 AST 로 고정한다.
    """
    tree = ast.parse((_SRC / "api/main.py").read_text(encoding="utf-8"))
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "GeneralChatUseCase"
    ]
    assert calls, "GeneralChatUseCase construction not found"
    for c in calls:
        kws = {k.arg for k in c.keywords}
        assert {"tool_access_resolver", "tool_id_resolver"} <= kws


def test_general_chat_rest_and_ws_share_factory():
    src = (_SRC / "api/main.py").read_text(encoding="utf-8")
    assert "app.dependency_overrides[get_general_chat_use_case] = create_general_chat_use_case_factory()" in src
    compact = " ".join(src.split())
    assert (
        "app.dependency_overrides[get_ws_general_chat_use_case] = ( create_general_chat_use_case_factory()"
        in compact
    )
