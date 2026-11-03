"""AST 계약 — ANSWER_COMPLETED payload 는 `_answer_payload()` 만 만든다.

agent-run-feedback-wiring Design §4.3 / D-02. 분기 4곳(정상·승인 대기·차단·강등)이
흩어져 있어, 새 분기가 헬퍼를 우회하면 그 턴만 assistant_message_id 가 빠진다.
`_build_event(..., AgentRunEventType.ANSWER_COMPLETED, ..., payload)` 의 payload 인자는
(a) `_answer_payload(...)` 호출이거나 (b) 같은 함수 안에서 `_answer_payload(...)` 로
대입된 이름이어야 한다.
"""
import ast
from pathlib import Path

SRC = (
    Path(__file__).resolve().parents[3]
    / "src" / "application" / "agent_builder" / "run_agent_use_case.py"
)
HELPER = "_answer_payload"
MIN_SITES = 3


def _is_answer_completed(arg: ast.AST) -> bool:
    return (
        isinstance(arg, ast.Attribute)
        and arg.attr == "ANSWER_COMPLETED"
        and isinstance(arg.value, ast.Name)
        and arg.value.id == "AgentRunEventType"
    )


def _is_helper_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == HELPER
    )


def _helper_assigned_names(func: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if _is_helper_call(node.value):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(t.id for t in targets if isinstance(t, ast.Name))
    return names


def _violations() -> tuple[int, list[str]]:
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    sites = 0
    bad: list[str] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        ok_names = _helper_assigned_names(func)
        for node in ast.walk(func):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_build_event"):
                continue
            if not any(_is_answer_completed(a) for a in node.args):
                continue
            sites += 1
            payload = node.args[-1] if len(node.args) >= 4 else None
            if payload is None:
                bad.append(f"L{node.lineno}: payload 인자 없음")
            elif _is_helper_call(payload):
                continue
            elif isinstance(payload, ast.Name) and payload.id in ok_names:
                continue
            else:
                bad.append(f"L{node.lineno}: payload 가 {HELPER}() 를 거치지 않음")
    return sites, bad


def test_every_answer_completed_payload_goes_through_helper() -> None:
    sites, bad = _violations()
    assert sites >= MIN_SITES, f"ANSWER_COMPLETED 생성 지점 {sites}곳 — 탐지 패턴 점검"
    assert not bad, "\n".join(bad)
