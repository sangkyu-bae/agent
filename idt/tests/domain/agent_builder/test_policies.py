"""AgentBuilderPolicy / UpdateAgentPolicy 단위 테스트 — mock 금지."""
import pytest

from src.domain.agent_builder.policies import AgentBuilderPolicy, UpdateAgentPolicy


class TestAgentBuilderPolicy:
    # ── validate_tool_count ─────────────────────────────────────

    def test_validate_tool_count_one_passes(self):
        AgentBuilderPolicy.validate_tool_count(1)  # 예외 없음

    def test_validate_tool_count_max_passes(self):
        AgentBuilderPolicy.validate_tool_count(5)  # 예외 없음

    def test_validate_tool_count_zero_raises(self):
        with pytest.raises(ValueError, match="최소"):
            AgentBuilderPolicy.validate_tool_count(0)

    def test_validate_tool_count_over_max_raises(self):
        with pytest.raises(ValueError, match="최대"):
            AgentBuilderPolicy.validate_tool_count(6)

    # ── validate_system_prompt ──────────────────────────────────

    def test_validate_system_prompt_normal_passes(self):
        AgentBuilderPolicy.validate_system_prompt("짧은 프롬프트")

    def test_validate_system_prompt_at_limit_passes(self):
        AgentBuilderPolicy.validate_system_prompt("a" * 4000)

    def test_validate_system_prompt_over_limit_raises(self):
        with pytest.raises(ValueError, match="4000"):
            AgentBuilderPolicy.validate_system_prompt("a" * 4001)

    # ── validate_name ───────────────────────────────────────────

    def test_validate_name_normal_passes(self):
        AgentBuilderPolicy.validate_name("AI 뉴스 수집기")

    def test_validate_name_empty_raises(self):
        with pytest.raises(ValueError, match="비어"):
            AgentBuilderPolicy.validate_name("")

    def test_validate_name_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="비어"):
            AgentBuilderPolicy.validate_name("   ")

    def test_validate_name_over_limit_raises(self):
        with pytest.raises(ValueError, match="200"):
            AgentBuilderPolicy.validate_name("a" * 201)


class TestUpdateAgentPolicy:
    def test_validate_update_active_status_passes(self):
        UpdateAgentPolicy.validate_update(status="active", system_prompt="정상 프롬프트")

    def test_validate_update_inactive_status_raises(self):
        with pytest.raises(ValueError, match="비활성화"):
            UpdateAgentPolicy.validate_update(status="inactive", system_prompt=None)

    def test_validate_update_system_prompt_over_limit_raises(self):
        with pytest.raises(ValueError, match="4000"):
            UpdateAgentPolicy.validate_update(status="active", system_prompt="a" * 4001)

    def test_validate_update_none_system_prompt_passes(self):
        UpdateAgentPolicy.validate_update(status="active", system_prompt=None)
