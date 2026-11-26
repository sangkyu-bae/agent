"""reference_context 호출자 opt-in 계약 — stock-analysis-agents DD5.

RunAgentUseCase 호출자 opt-in 게이팅 규칙(inject_memory·supplemental_grant 선례)과 같다:
- `reference_context=` 를 넘기는 곳은 시장 분석 어댑터 하나뿐이다
- HTTP·WS 라우트는 이 필드를 만들지 않는다 (요청 스키마로도 들어올 수 없다)
- `_prepare_graph` 는 실제로 덧붙이는 함수를 부른다
"""

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
_ALLOWED = {"infrastructure/market_analysis/adapters/agent_runner.py"}


def _func_name(node: ast.Call) -> str:
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return ""


def _callers(*, only_request: bool) -> set[str]:
    found = set()
    for path in _SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not any(kw.arg == "reference_context" for kw in node.keywords):
                continue
            if only_request and _func_name(node) != "RunAgentRequest":
                continue
            found.add(path.relative_to(_SRC).as_posix())
    return found


def test_only_market_analysis_adapter_builds_request_with_it():
    """코어 RunAgentRequest(reference_context=...) 를 만드는 곳은 어댑터 하나뿐."""
    assert _callers(only_request=True) == _ALLOWED


def test_core_outside_market_analysis_never_passes_it():
    """시장 분석 모듈 밖 코어는 이 인자를 쓰지 않는다 (agent_builder 내부 전달은 예외).

    모듈 안의 `AgentRunner.run(reference_context=...)`
    는 포트 인자라 여기서 세지 않는다.
    """
    callers = {
        c
        for c in _callers(only_request=False)
        if "market_analysis" not in c and not c.startswith("application/agent_builder/")
    }
    assert callers == set(), sorted(callers)


def test_http_routes_never_set_it():
    for rel in ("api/routes/agent_builder_router.py", "api/routes/ws_router.py"):
        assert "reference_context" not in (_SRC / rel).read_text(encoding="utf-8"), rel


def test_prepare_graph_attaches_the_context():
    tree = ast.parse(
        (_SRC / "application/agent_builder/run_agent_use_case.py").read_text(
            encoding="utf-8"
        )
    )
    prepare = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_prepare_graph"
    )
    names = {
        n.func.id
        for n in ast.walk(prepare)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "attach_reference_context" in names
