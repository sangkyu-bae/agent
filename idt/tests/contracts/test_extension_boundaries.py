"""코어 확장 지점 계약 (graph-rag-foundation Plan SC-8·SC-9, module-1).

C1  코어 소스는 graph_rag 패키지를 import 하지 않는다 (모듈 제거 가능)
C2  대화 라우트(WS·REST·SSE)만 supplemental_grant 를 만들어 넘긴다
C3  비대화 호출자(웹훅·백그라운드·스케줄·RAGAS)는 supplemental_grant 를 모른다
C4  RunAgentUseCase → compile → (서브에이전트 재귀·도구 생성) 키워드 체인이 끊기지 않는다
C5  에이전트 저장 경로 3곳(create·update·fork)은 use_graph 정리를 호출한다
"""
import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
_EXTENSION_PKGS = ("graph_rag",)
# 확장 모듈 자신과 조립 지점(main.py·*_di.py)은 import 해도 된다.
_ALLOWED_IMPORTERS = ("api/main.py",)


def _is_extension_file(rel: str) -> bool:
    """확장 모듈 소유 파일: graph_rag/ 패키지 + 라우터·스키마 등 *graph_rag*.py."""
    return any(
        f"/{pkg}/" in f"/{rel}" or pkg in rel.rsplit("/", 1)[-1]
        for pkg in _EXTENSION_PKGS
    )


def _py_files():
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_SRC).as_posix()
        if _is_extension_file(rel):
            continue
        if rel in _ALLOWED_IMPORTERS or rel.endswith("_di.py"):
            continue
        yield rel, path


def _imported_modules(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


def test_C1_core_does_not_import_extension_packages():
    offenders = []
    for rel, path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for mod in _imported_modules(tree):
            if any(f".{pkg}" in f".{mod}" for pkg in _EXTENSION_PKGS):
                offenders.append(f"{rel} -> {mod}")
    assert offenders == [], offenders


def _calls_with_kw(rel: str, attrs: tuple[str, ...], kw: str) -> list[ast.Call]:
    tree = ast.parse((_SRC / rel).read_text(encoding="utf-8"))
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in attrs
        and any(k.arg == kw for k in node.keywords)
    ]


def test_C2_conversation_routes_pass_grant():
    expected = {"api/routes/ws_router.py": 1, "api/routes/agent_builder_router.py": 2}
    for rel, count in expected.items():
        calls = _calls_with_kw(rel, ("stream", "execute"), "supplemental_grant")
        assert len(calls) >= count, f"{rel}: grant 전달 {len(calls)} < {count}"


def test_C3_non_conversation_callers_never_grant():
    for rel in (
        "application/agent_webhook/invoke_webhook_agent_use_case.py",
        "application/background_job/worker.py",
        "application/agent_schedule/trigger_due_schedules_use_case.py",
        "infrastructure/ragas/target_executor.py",
        "application/approval/decide_use_case.py",
        "application/approval/execute_scheduler.py",
    ):
        src = (_SRC / rel).read_text(encoding="utf-8")
        assert "supplemental_grant" not in src, f"{rel} 가 보조 검색을 opt-in 했다"
        assert "SupplementalGrant" not in src, f"{rel} 가 grant 를 만든다"


def test_C3b_ragas_headless_runner_in_main_never_grants():
    tree = ast.parse((_SRC / "api/main.py").read_text(encoding="utf-8"))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_run_agent_headless"
    )
    assert "supplemental_grant" not in ast.unparse(fn)


def test_C4_keyword_chain_is_connected():
    run_uc = "application/agent_builder/run_agent_use_case.py"
    assert _calls_with_kw(run_uc, ("_prepare_graph",), "supplemental_grant")
    assert _calls_with_kw(run_uc, ("stream",), "supplemental_grant")  # execute → stream
    compiler = "application/agent_builder/workflow_compiler.py"
    # 도구 생성은 grant 가 있을 때만 키워드를 펼쳐 넘긴다(기존 fake 팩토리 호환)
    assert '{"supplemental_grant": supplemental_grant}' in (_SRC / compiler).read_text(
        encoding="utf-8"
    )
    assert _calls_with_kw(compiler, ("_compile_sub_agent",), "supplemental_grant")
    assert _calls_with_kw(compiler, ("compile",), "supplemental_grant")  # 재귀


def test_C5_agent_save_paths_strip_flag():
    for rel in (
        "application/agent_builder/create_agent_use_case.py",
        "application/agent_builder/update_agent_use_case.py",
        "application/agent_builder/fork_agent_use_case.py",
    ):
        src = (_SRC / rel).read_text(encoding="utf-8")
        assert "strip_unexposed_graph_flag(" in src, f"{rel} 가 use_graph 를 정리하지 않는다"
