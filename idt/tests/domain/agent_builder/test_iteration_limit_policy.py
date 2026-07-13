"""IterationLimitPolicy + AgentDefinition.max_iterations 단위 테스트.

agent-recursion-limit Design D1/D2 — 반복 한도 단일 소스 도메인 규칙.
"""
import uuid
from datetime import datetime, timezone

import pytest

from src.domain.agent_builder.policies import IterationLimitPolicy
from src.domain.agent_builder.schemas import AgentDefinition, SupervisorConfig


def _make_agent(**overrides) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    base = dict(
        id=str(uuid.uuid4()),
        user_id="user-1",
        name="테스트",
        description="설명",
        system_prompt="프롬프트",
        flow_hint="힌트",
        workers=[],
        llm_model_id="model-1",
        status="active",
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return AgentDefinition(**base)


class TestIterationLimitPolicyValidate:
    def test_min_boundary_accepted(self):
        IterationLimitPolicy.validate(10)  # no raise

    def test_max_boundary_accepted(self):
        IterationLimitPolicy.validate(1000)  # no raise

    def test_below_min_rejected(self):
        with pytest.raises(ValueError, match="10"):
            IterationLimitPolicy.validate(9)

    def test_above_max_rejected(self):
        with pytest.raises(ValueError, match="1000"):
            IterationLimitPolicy.validate(1001)

    def test_default_is_25(self):
        assert IterationLimitPolicy.DEFAULT == 25
        IterationLimitPolicy.validate(IterationLimitPolicy.DEFAULT)


class TestDeriveRecursionLimit:
    def test_default_derivation(self):
        """25회 → 25×10+20 = 270 스텝 (D3)."""
        assert IterationLimitPolicy.derive_recursion_limit(25) == 270

    def test_derivation_is_monotonic_and_above_state_guard(self):
        for v in (10, 25, 100, 1000):
            derived = IterationLimitPolicy.derive_recursion_limit(v)
            # 최악 경로(반복당 5스텝 + 재시도 8스텝)보다 항상 커야 state 가드 선발동
            assert derived > v * 8


class TestSubAgentLimit:
    def test_half_of_parent(self):
        assert IterationLimitPolicy.sub_agent_limit(25) == 12

    def test_floor_guaranteed(self):
        assert IterationLimitPolicy.sub_agent_limit(10) == 5
        assert IterationLimitPolicy.sub_agent_limit(6) == 5

    def test_large_parent(self):
        assert IterationLimitPolicy.sub_agent_limit(1000) == 500


class TestAgentDefinitionMaxIterations:
    def test_default_is_25(self):
        agent = _make_agent()
        assert agent.max_iterations == 25

    def test_custom_value_accepted(self):
        agent = _make_agent(max_iterations=100)
        assert agent.max_iterations == 100

    def test_below_range_rejected(self):
        with pytest.raises(ValueError):
            _make_agent(max_iterations=9)

    def test_above_range_rejected(self):
        with pytest.raises(ValueError):
            _make_agent(max_iterations=1001)

    def test_apply_update_changes_value(self):
        agent = _make_agent()
        agent.apply_update(
            system_prompt=None, name=None, max_iterations=50,
        )
        assert agent.max_iterations == 50

    def test_apply_update_none_keeps_value(self):
        agent = _make_agent(max_iterations=77)
        agent.apply_update(system_prompt=None, name=None)
        assert agent.max_iterations == 77

    def test_apply_update_out_of_range_rejected(self):
        agent = _make_agent()
        with pytest.raises(ValueError):
            agent.apply_update(
                system_prompt=None, name=None, max_iterations=5,
            )


class TestSupervisorConfigDefault:
    def test_default_max_iterations_follows_policy(self):
        """D1: 하드코딩 10 → 정책 기본값 25로 상향."""
        assert SupervisorConfig().max_iterations == IterationLimitPolicy.DEFAULT
