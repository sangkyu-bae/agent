"""RunAgentUseCase._build_graph_config 단위 테스트.

Design agent-run-langsmith-per-agent-project §3.2.2 / §4.2.
graph_config에 run_name=에이전트명, tags·metadata에 agent_name,
tracer/usage-callback 합성, run_id 조건부 포함을 검증한다.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.application.agent_builder import run_agent_use_case as mod
from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.agent_run.value_objects import RunId


def _make_agent(name: str = "여신심사봇") -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()),
        user_id="user-1",
        name=name,
        description="설명",
        system_prompt="시스템 프롬프트",
        flow_hint="힌트",
        workers=[WorkerDefinition("tavily_search", "search_worker", "검색", 0)],
        llm_model_id="model-1",
        status="active",
        created_at=now,
        updated_at=now,
    )


class TestGraphConfig:
    def test_has_run_name_tags_and_agent_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mod, "make_agent_run_tracer", lambda *a, **k: None)
        agent = _make_agent("여신심사봇")

        cfg = RunAgentUseCase._build_graph_config(
            agent=agent, session_id="s-1", run_id=None,
            user_id="user-1", callback=None,
        )

        assert cfg["run_name"] == "여신심사봇"
        assert "여신심사봇" in cfg["tags"]
        assert agent.id in cfg["tags"]
        assert cfg["metadata"]["agent_name"] == "여신심사봇"
        assert cfg["metadata"]["agent_id"] == agent.id
        assert cfg["configurable"]["thread_id"] == "s-1"
        # tracker/run_id None → run_id 키 없음, callbacks 없음
        assert "run_id" not in cfg["metadata"]
        assert "callbacks" not in cfg

    def test_callbacks_include_tracer_when_key_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sentinel = MagicMock(name="tracer")
        monkeypatch.setattr(mod, "make_agent_run_tracer", lambda *a, **k: sentinel)
        agent = _make_agent()

        cfg = RunAgentUseCase._build_graph_config(
            agent=agent, session_id="s-1", run_id=None,
            user_id="user-1", callback=None,
        )

        assert cfg["callbacks"] == [sentinel]

    def test_callbacks_and_run_id_with_observability(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tracer = MagicMock(name="tracer")
        usage_cb = MagicMock(name="usage_callback")
        monkeypatch.setattr(mod, "make_agent_run_tracer", lambda *a, **k: tracer)
        agent = _make_agent()
        run_id = RunId(str(uuid.uuid4()))

        cfg = RunAgentUseCase._build_graph_config(
            agent=agent, session_id="s-1", run_id=run_id,
            user_id="user-1", callback=usage_cb,
        )

        assert cfg["metadata"]["run_id"] == run_id.value
        # tracer 먼저, usage callback 다음 (전역 auto-tracer 억제 목적)
        assert cfg["callbacks"] == [tracer, usage_cb]
