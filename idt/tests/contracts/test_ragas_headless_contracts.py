"""RAGAS 헤드리스 실행 계약 — 정적 검사.

1) LoggerInterface 에는 exception() 이 없다. src 어디서도 `<logger>.exception(` 을
   부르지 않는다. 부르면 오류 처리부가 AttributeError 로 죽어 상태 갱신을 건너뛴다
   (RAGAS run 이 running 으로 영원히 남던 결함).
2) RAGAS 에이전트 평가 실행기는 평가 요청자의 AuthContext 를 조립해 넘긴다.
   auth_ctx 가 없으면 내부 문서 검색 도구가 public_anonymous 로 판단해 검색을
   거부하므로, RAG 에이전트가 검색 없이 채점된다.
"""
import ast
import re
from pathlib import Path

from src.domain.logging.interfaces.logger_interface import LoggerInterface

_SRC = Path(__file__).resolve().parents[2] / "src"
_LOGGER_EXCEPTION = re.compile(r"\b(?:self\.)?_?logger\.exception\(")


def test_logger_interface_has_no_exception_method():
    assert not hasattr(LoggerInterface, "exception")


def test_src_never_calls_logger_exception():
    offenders = [
        f"{p.relative_to(_SRC)}:{i}"
        for p in _SRC.rglob("*.py")
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if _LOGGER_EXCEPTION.search(line)
    ]
    assert offenders == [], (
        "logger.exception 호출 — logger.error(..., exception=e) 로 바꿀 것: "
        f"{offenders}"
    )


def _headless_fn() -> ast.AsyncFunctionDef:
    tree = ast.parse((_SRC / "api/main.py").read_text(encoding="utf-8"))
    return next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_run_agent_headless"
    )


def test_ragas_headless_runner_passes_assembled_auth_ctx():
    fn = _headless_fn()
    auth_kws = [
        k.value for n in ast.walk(fn) if isinstance(n, ast.Call)
        for k in n.keywords if k.arg == "auth_ctx"
    ]
    assert len(auth_kws) == 1, "run_uc.execute 에 auth_ctx 를 넘겨야 한다"
    assert isinstance(auth_kws[0], ast.Name)
    assembled = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == auth_kws[0].id for t in n.targets)
    ]
    assert assembled, "auth_ctx 는 실행기 안에서 조립한 값이어야 한다"
    assert "assemble_user_auth_context" in ast.unparse(assembled[0].value)
