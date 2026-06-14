"""SqlAlchemyAgentRunRepository mapper 정규화 검증.

fix-tracker-naive-aware-datetime Design §6.2:
- _to_utc 헬퍼 4 케이스
- 4개 _*_to_domain mapper의 datetime 필드가 항상 aware UTC 반환

배경: MySQL DATETIME 컬럼은 tzinfo를 저장하지 않으므로 SQLAlchemy fetch 시
naive datetime이 반환된다. 도메인 엔티티는 항상 aware UTC를 가정하므로
mapper 단계에서 정규화한다.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from src.infrastructure.persistence.models.agent_run import (
    AgentRunModel,
    AgentRunStepModel,
    RetrievalSourceModel,
    ToolCallModel,
)
from src.infrastructure.persistence.repositories.agent_run_repository import (
    SqlAlchemyAgentRunRepository,
    _to_utc,
)


RUN_ID = "11111111-1111-1111-1111-111111111111"
STEP_ID = "22222222-2222-2222-2222-222222222222"
TOOL_CALL_ID = "33333333-3333-3333-3333-333333333333"
RETRIEVAL_ID = "44444444-4444-4444-4444-444444444444"


class TestToUtcHelper:
    def test_returns_none_for_none(self) -> None:
        assert _to_utc(None) is None

    def test_naive_datetime_becomes_aware_utc(self) -> None:
        naive = datetime(2026, 5, 24, 6, 17, 9)
        result = _to_utc(naive)
        assert result is not None
        assert result.tzinfo == timezone.utc
        # wall clock 값은 변경되지 않아야 함
        assert result.year == 2026 and result.month == 5 and result.day == 24
        assert result.hour == 6 and result.minute == 17 and result.second == 9

    def test_aware_utc_returned_as_is_idempotent(self) -> None:
        aware = datetime(2026, 5, 24, 6, 17, 9, tzinfo=timezone.utc)
        result = _to_utc(aware)
        assert result == aware
        assert result is not None and result.tzinfo == timezone.utc

    def test_aware_non_utc_preserved_not_converted(self) -> None:
        kst = timezone(timedelta(hours=9))
        aware_kst = datetime(2026, 5, 24, 15, 17, 9, tzinfo=kst)
        result = _to_utc(aware_kst)
        # 정책: aware는 변환하지 않고 그대로 보존 (UTC로 강제 변환하지 않음)
        assert result == aware_kst
        assert result is not None and result.tzinfo == kst


def _make_repo() -> SqlAlchemyAgentRunRepository:
    """Mapper만 호출하므로 session은 None으로 둬도 무방."""
    return SqlAlchemyAgentRunRepository(session=None)  # type: ignore[arg-type]


class TestRunToDomain:
    def test_naive_started_at_becomes_aware_utc(self) -> None:
        row = AgentRunModel(
            id=RUN_ID,
            conversation_id="conv-1",
            user_id="user-1",
            agent_id="agent-1",
            llm_model_id=None,
            user_message_id=None,
            status="SUCCESS",
            langgraph_thread_id="conv-1",
            langsmith_trace_id=None,
            langsmith_run_url=None,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            total_cost_usd=Decimal("0"),
            llm_call_count=0,
            started_at=datetime(2026, 5, 24, 6, 17, 9),  # naive (MySQL fetch 시뮬레이션)
            ended_at=datetime(2026, 5, 24, 6, 17, 11),   # naive
            latency_ms=2000,
            error_message=None,
            error_stack=None,
        )
        repo = _make_repo()
        domain = repo._run_to_domain(row)
        assert domain.started_at.tzinfo == timezone.utc
        assert domain.ended_at is not None
        assert domain.ended_at.tzinfo == timezone.utc

    def test_ended_at_none_stays_none(self) -> None:
        row = AgentRunModel(
            id=RUN_ID,
            conversation_id="conv-1",
            user_id="user-1",
            agent_id="agent-1",
            llm_model_id=None,
            user_message_id=None,
            status="RUNNING",
            langgraph_thread_id="conv-1",
            langsmith_trace_id=None,
            langsmith_run_url=None,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            total_cost_usd=Decimal("0"),
            llm_call_count=0,
            started_at=datetime(2026, 5, 24, 6, 17, 9),
            ended_at=None,
            latency_ms=None,
            error_message=None,
            error_stack=None,
        )
        repo = _make_repo()
        domain = repo._run_to_domain(row)
        assert domain.ended_at is None
        assert domain.started_at.tzinfo == timezone.utc


class TestStepToDomain:
    def test_naive_started_and_ended_become_aware_utc(self) -> None:
        row = AgentRunStepModel(
            id=STEP_ID,
            run_id=RUN_ID,
            step_index=1,
            node_name="answer",
            node_type="WORKER",
            llm_model_id=None,
            status="SUCCESS",
            input_summary=None,
            output_summary=None,
            started_at=datetime(2026, 5, 24, 6, 17, 9),  # naive
            ended_at=datetime(2026, 5, 24, 6, 17, 11),   # naive
            latency_ms=2000,
            error_text=None,
        )
        repo = _make_repo()
        domain = repo._step_to_domain(row)
        assert domain.started_at.tzinfo == timezone.utc
        assert domain.ended_at is not None
        assert domain.ended_at.tzinfo == timezone.utc

    def test_ended_at_none_stays_none(self) -> None:
        row = AgentRunStepModel(
            id=STEP_ID,
            run_id=RUN_ID,
            step_index=1,
            node_name="answer",
            node_type="WORKER",
            llm_model_id=None,
            status="STARTED",
            input_summary=None,
            output_summary=None,
            started_at=datetime(2026, 5, 24, 6, 17, 9),
            ended_at=None,
            latency_ms=None,
            error_text=None,
        )
        repo = _make_repo()
        domain = repo._step_to_domain(row)
        assert domain.ended_at is None
        assert domain.started_at.tzinfo == timezone.utc


class TestToolToDomain:
    def test_naive_created_at_becomes_aware_utc(self) -> None:
        row = ToolCallModel(
            id=TOOL_CALL_ID,
            run_id=RUN_ID,
            step_id=None,
            tool_name="search",
            llm_model_id=None,
            arguments_json=None,
            result_summary=None,
            result_json=None,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            total_cost_usd=None,
            latency_ms=None,
            status="SUCCESS",
            error_text=None,
            created_at=datetime(2026, 5, 24, 6, 17, 9),  # naive
        )
        repo = _make_repo()
        domain = repo._tool_to_domain(row)
        assert domain.created_at.tzinfo == timezone.utc


class TestRetrievalToDomain:
    def test_naive_created_at_becomes_aware_utc(self) -> None:
        row = RetrievalSourceModel(
            id=RETRIEVAL_ID,
            run_id=RUN_ID,
            tool_call_id=None,
            collection_name="docs",
            document_id=None,
            chunk_id=None,
            score=Decimal("0.85"),
            rank_index=1,
            content_preview=None,
            metadata_json=None,
            created_at=datetime(2026, 5, 24, 6, 17, 9),  # naive
        )
        repo = _make_repo()
        domain = repo._retrieval_to_domain(row)
        assert domain.created_at.tzinfo == timezone.utc
