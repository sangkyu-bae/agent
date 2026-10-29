"""main.py RunAgentUseCase 조립에 memory_assembler 배선 — agent-memory-injection Design §6.3 D10 (W1).

런타임 조립은 DB·LLM 이 필요해 소스 계약으로 고정한다 (ast-source-contract-tests).
General Chat 과 같은 get_memory_assembler() 싱글톤을 공유해야 한다.
"""
import ast
from pathlib import Path


def _run_agent_uc_keywords() -> dict[str, ast.expr]:
    src = (Path(__file__).resolve().parents[2] / "src" / "api" / "main.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "RunAgentUseCase"
        ):
            return {kw.arg: kw.value for kw in node.keywords}
    raise AssertionError("RunAgentUseCase(...) 생성 호출이 main.py 에 없다")


def test_W1_run_agent_uc_receives_memory_assembler_singleton():
    kws = _run_agent_uc_keywords()
    assert "memory_assembler" in kws, "memory_assembler kwarg 가 배선되지 않았다"
    value = kws["memory_assembler"]
    assert isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
    assert value.func.id == "get_memory_assembler"


_SRC = Path(__file__).resolve().parents[2] / "src"


def _run_calls_with_auth_ctx(rel: str) -> list[ast.Call]:
    """`<obj>.stream(...)`/`<obj>.execute(...)` 중 auth_ctx= 를 넘기는 호출만."""
    tree = ast.parse((_SRC / rel).read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in ("stream", "execute"):
            continue
        if any(kw.arg == "auth_ctx" for kw in node.keywords):
            found.append(node)
    return found


def _passes_inject_memory_true(call: ast.Call) -> bool:
    return any(
        kw.arg == "inject_memory"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value is True
        for kw in call.keywords
    )


def test_W2_conversation_routes_opt_in_memory_injection():
    """Act-1 (Analysis G1): WS·REST·SSE 대화 라우트는 inject_memory=True 를 넘긴다."""
    expected = {"api/routes/ws_router.py": 1, "api/routes/agent_builder_router.py": 2}
    for rel, count in expected.items():
        calls = [
            c for c in _run_calls_with_auth_ctx(rel) if _passes_inject_memory_true(c)
        ]
        assert len(calls) >= count, f"{rel}: inject_memory=True 호출 {len(calls)} < {count}"


def test_W3_non_conversation_callers_do_not_opt_in():
    """웹훅·백그라운드 잡·스케줄은 inject_memory 를 넘기지 않는다 (기본 False)."""
    for rel in (
        "application/agent_webhook/invoke_webhook_agent_use_case.py",
        "application/background_job/worker.py",
        "application/agent_schedule/trigger_due_schedules_use_case.py",
    ):
        src = (_SRC / rel).read_text(encoding="utf-8")
        assert "inject_memory" not in src, f"{rel} 가 메모리 주입을 opt-in 했다"
