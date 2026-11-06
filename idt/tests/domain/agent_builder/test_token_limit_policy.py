"""TokenLimitPolicy + AgentDefinition.token_limit 단위 테스트.

agent-token-limit Design D2/D3 — 토큰 예산 단일 소스 도메인 규칙.
Plan SC: SC-5 (범위 밖 값은 도메인 ValueError).
"""
import uuid
from datetime import datetime, timezone

import pytest

from src.domain.agent_builder.policies import TokenLimitPolicy
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


class TestTokenLimitPolicyValidate:
    def test_constants(self):
        """D2: 기본 50000, 범위 8000~500000 (사용자 결정 2026-11-05)."""
        assert TokenLimitPolicy.DEFAULT == 50000
        assert TokenLimitPolicy.MIN == 8000
        assert TokenLimitPolicy.MAX == 500000

    def test_min_boundary_accepted(self):
        TokenLimitPolicy.validate(8000)

    def test_max_boundary_accepted(self):
        TokenLimitPolicy.validate(500000)

    def test_below_min_rejected(self):
        with pytest.raises(ValueError, match="8000"):
            TokenLimitPolicy.validate(7999)

    def test_above_max_rejected(self):
        with pytest.raises(ValueError, match="500000"):
            TokenLimitPolicy.validate(500001)

    def test_default_is_valid(self):
        TokenLimitPolicy.validate(TokenLimitPolicy.DEFAULT)


class TestAgentDefinitionTokenLimit:
    def test_default_follows_policy(self):
        assert _make_agent().token_limit == TokenLimitPolicy.DEFAULT

    def test_custom_value_accepted(self):
        assert _make_agent(token_limit=120000).token_limit == 120000

    def test_below_range_rejected(self):
        with pytest.raises(ValueError):
            _make_agent(token_limit=7999)

    def test_above_range_rejected(self):
        with pytest.raises(ValueError):
            _make_agent(token_limit=500001)

    def test_apply_update_changes_value(self):
        agent = _make_agent()
        agent.apply_update(system_prompt=None, name=None, token_limit=60000)
        assert agent.token_limit == 60000

    def test_apply_update_none_keeps_value(self):
        agent = _make_agent(token_limit=77000)
        agent.apply_update(system_prompt=None, name=None)
        assert agent.token_limit == 77000

    def test_apply_update_out_of_range_rejected(self):
        agent = _make_agent()
        with pytest.raises(ValueError):
            agent.apply_update(system_prompt=None, name=None, token_limit=100)

    def test_max_iterations_still_validated_independently(self):
        """반복 한도 검증은 그대로 — 두 정책은 독립이다."""
        with pytest.raises(ValueError):
            _make_agent(token_limit=50000, max_iterations=9)


class TestSupervisorConfigTokenLimitDefault:
    def test_default_follows_policy(self):
        """D3: 하드코딩 8000 → 정책 기본값."""
        assert SupervisorConfig().token_limit == TokenLimitPolicy.DEFAULT
