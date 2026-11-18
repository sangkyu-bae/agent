"""DefaultTargetExecutor — 보조 검색 opt-in 은 켰을 때만 실행기에 넘긴다(module-7).

기존 실행기(오버라이드 인자만 아는 fake·스윕)는 키워드를 받지 않아도 깨지지 않는다.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.domain.ragas.value_objects import EvalConfig, MetricType, TestCase
from src.infrastructure.ragas.target_executor import (
    AgentRunOutcome,
    DefaultTargetExecutor,
)


def _executor(runner):
    return DefaultTargetExecutor(
        qdrant_client=MagicMock(),
        embedding=MagicMock(),
        agent_runner=runner,
        logger=MagicMock(),
    )


def _config(**over):
    return EvalConfig(metrics=[MetricType("answer_relevancy")], agent_id="a1", **over)


@pytest.mark.asyncio
async def test_allow_supplemental_is_forwarded_only_when_on():
    runner = AsyncMock(return_value=AgentRunOutcome(answer="ok"))
    ex = _executor(runner)
    await ex.execute(
        "agent", _config(allow_supplemental=True), TestCase(question="q"), "1", "r"
    )
    assert runner.await_args.kwargs["allow_supplemental"] is True

    await ex.execute("agent", _config(), TestCase(question="q"), "1", "r")
    assert "allow_supplemental" not in runner.await_args.kwargs
