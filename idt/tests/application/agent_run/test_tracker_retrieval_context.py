"""retrieval-observability §6-1/2: record_retrieval 쿼리 컨텍스트 확장 + attach_user_message.

Design §4.1 — 신규 kwargs는 전부 optional (하위호환), attach_user_message는 best-effort.
"""
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.entities import RetrievalSource
from src.domain.agent_run.value_objects import RunId


RUN_ID = "11111111-1111-1111-1111-111111111111"


class _FakeSessionFactory:
    def __init__(self) -> None:
        self.failing = False

    def __call__(self) -> "_FakeSession":
        return _FakeSession(self)


class _FakeSession:
    def __init__(self, parent: _FakeSessionFactory) -> None:
        self._parent = parent

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    def begin(self) -> "_FakeTransaction":
        return _FakeTransaction()

    async def execute(self, *a: Any, **k: Any) -> MagicMock:
        return MagicMock()

    async def flush(self) -> None:
        if self._parent.failing:
            raise RuntimeError("flush failed")

    def add(self, _obj: Any) -> None:
        if self._parent.failing:
            raise RuntimeError("add failed")


class _FakeTransaction:
    async def __aenter__(self) -> "_FakeTransaction":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None


def _make_tracker(failing: bool = False) -> tuple[RunTracker, MagicMock]:
    factory = _FakeSessionFactory()
    factory.failing = failing
    logger = MagicMock()
    tracker = RunTracker(
        session_factory=factory,
        cost_calculator=MagicMock(),
        model_name_resolver=MagicMock(),
        logger=logger,
    )
    return tracker, logger


class TestRecordRetrievalQueryContext:
    """신규 필드(search_query 등) 저장 + 미전달 시 None 하위호환."""

    @pytest.mark.asyncio
    async def test_new_fields_passed_to_repository(self) -> None:
        tracker, _ = _make_tracker()
        saved: list[RetrievalSource] = []

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as repo_cls:
            repo = repo_cls.return_value
            repo.save_retrieval = AsyncMock(side_effect=lambda s: saved.append(s))

            await tracker.record_retrieval(
                run_id=RunId(RUN_ID),
                tool_call_id="tc-1",
                collection_name="finance-docs",
                chunk_id="chunk-1",
                score=0.92,
                rank_index=1,
                search_query="재작성된 검색 쿼리",
                query_source="multi_query",
                search_mode="hybrid",
                bm25_score=5.5,
                vector_score=0.9,
                bm25_rank=1,
                vector_rank=2,
                fusion_source="both",
            )

        assert len(saved) == 1
        src = saved[0]
        assert src.search_query == "재작성된 검색 쿼리"
        assert src.query_source == "multi_query"
        assert src.search_mode == "hybrid"
        assert src.bm25_score == pytest.approx(5.5)
        assert src.vector_score == pytest.approx(0.9)
        assert src.bm25_rank == 1
        assert src.vector_rank == 2
        assert src.fusion_source == "both"

    @pytest.mark.asyncio
    async def test_new_fields_default_none_backward_compat(self) -> None:
        """기존 호출 시그니처(신규 kwargs 미전달)가 그대로 동작."""
        tracker, _ = _make_tracker()
        saved: list[RetrievalSource] = []

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as repo_cls:
            repo = repo_cls.return_value
            repo.save_retrieval = AsyncMock(side_effect=lambda s: saved.append(s))

            await tracker.record_retrieval(
                run_id=RunId(RUN_ID),
                tool_call_id=None,
                collection_name="finance-docs",
                chunk_id="chunk-1",
            )

        src = saved[0]
        assert src.search_query is None
        assert src.query_source is None
        assert src.search_mode is None
        assert src.bm25_score is None
        assert src.vector_score is None
        assert src.fusion_source is None


class TestAttachUserMessage:
    """Design D2: deferred attach — best-effort UPDATE."""

    @pytest.mark.asyncio
    async def test_attach_calls_repository(self) -> None:
        tracker, _ = _make_tracker()

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as repo_cls:
            repo = repo_cls.return_value
            repo.attach_user_message = AsyncMock()

            await tracker.attach_user_message(RunId(RUN_ID), 42)

            repo.attach_user_message.assert_awaited_once()
            args = repo.attach_user_message.await_args
            assert args.args[0].value == RUN_ID
            assert args.args[1] == 42

    @pytest.mark.asyncio
    async def test_attach_failure_is_best_effort(self) -> None:
        """실패 시 raise 없이 warning 로그만."""
        tracker, logger = _make_tracker()

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as repo_cls:
            repo = repo_cls.return_value
            repo.attach_user_message = AsyncMock(side_effect=RuntimeError("DB down"))

            await tracker.attach_user_message(RunId(RUN_ID), 42)  # no raise

        assert logger.warning.called
