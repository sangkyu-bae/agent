"""전역 os.environ 오염 제거 회귀 테스트 — Design §4-2 / §8 (T-08).

`langsmith()` 는 `os.environ["LANGSMITH_TRACING"]` 을 **영구** 세팅하고 되돌리지
않는다. 그 결과 한 번 실행된 뒤의 모든 LangChain 호출이 마지막에 설정된
`LANGSMITH_PROJECT` 로 흘러간다 (Design §1-3).

여기서는 "전역을 건드리지 않는다"를 **소스 수준**으로 고정한다. 세 use case 는
DB·LLM 협력자가 많아 인스턴스화 비용이 크고, 전역 오염은 호출 시점이 아니라
import 시점의 배선 문제이기 때문이다.
"""
import ast
import os
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[3] / "src"

# Design §4-2 — 전역 `langsmith()` 를 버리기로 한 경로들.
_CLEANED = (
    "application/agent_builder/run_agent_use_case.py",
    "application/general_chat/use_case.py",
    "application/use_cases/analyze_excel_use_case.py",
)


def _calls_global_langsmith(path: Path) -> bool:
    """모듈 안에 `langsmith(...)` 호출이 남아 있는지 (AST, 주석/문자열 무시)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name == "langsmith":
                return True
    return False


@pytest.mark.parametrize("rel", _CLEANED)
def test_no_global_langsmith_call(rel: str) -> None:
    assert not _calls_global_langsmith(_SRC / rel), (
        f"{rel} 가 전역 langsmith() 를 호출한다 — per-run tracer 로 치환할 것 "
        "(Design §4-2)"
    )


@pytest.mark.parametrize("rel", _CLEANED)
def test_no_global_langsmith_import(rel: str) -> None:
    """import 가 남으면 되살아나기 쉽다 — 배선과 함께 제거한다."""
    tree = ast.parse((_SRC / rel).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "langsmith" not in imported, f"{rel} 에 전역 langsmith import 잔존"


class TestImportDoesNotPollute:
    """모듈 import 만으로 추적 환경변수가 바뀌지 않는다."""

    @pytest.mark.parametrize("rel", _CLEANED)
    def test_import_leaves_env_clean(
        self, rel: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LANGCHAIN_API_KEY", "lsv2_dummy_key_for_test")
        monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
        monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)

        module = "src." + rel.removesuffix(".py").replace("/", ".")
        __import__(module)

        assert os.environ.get("LANGSMITH_TRACING") is None
        assert os.environ.get("LANGSMITH_PROJECT") is None


class TestProjectNamesPreserved:
    """FR-06 — 치환하되 기존 프로젝트명은 그대로 유지한다."""

    def test_constants_exist(self) -> None:
        from src.infrastructure.langsmith.langsmith import (
            EXCEL_ANALYSIS_PROJECT_NAME,
            GENERAL_CHAT_PROJECT_NAME,
        )

        assert GENERAL_CHAT_PROJECT_NAME == "general-chat"
        assert EXCEL_ANALYSIS_PROJECT_NAME == "excel-analysis-agent"

    def test_general_chat_tracer_uses_fixed_project(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LANGCHAIN_API_KEY", "lsv2_dummy_key_for_test")
        from src.infrastructure.langsmith.langsmith import make_general_chat_tracer

        tracer = make_general_chat_tracer(tags=["general-chat"])
        assert tracer is not None
        assert tracer.project_name == "general-chat"

    def test_general_chat_tracer_none_without_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
        from src.infrastructure.langsmith.langsmith import make_general_chat_tracer

        assert make_general_chat_tracer() is None
