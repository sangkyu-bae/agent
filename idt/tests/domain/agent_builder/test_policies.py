"""AgentBuilderPolicy / UpdateAgentPolicy 단위 테스트 — mock 금지."""
import pytest

from src.domain.agent_builder.policies import AgentBuilderPolicy, UpdateAgentPolicy
from src.domain.agent_builder.schemas import WorkerDefinition


class TestAgentBuilderPolicy:
    # ── validate_tool_count ─────────────────────────────────────

    def test_validate_tool_count_one_passes(self):
        AgentBuilderPolicy.validate_tool_count(1)  # 예외 없음

    def test_validate_tool_count_max_passes(self):
        AgentBuilderPolicy.validate_tool_count(5)  # 예외 없음

    def test_validate_tool_count_zero_passes(self):
        # agent-instruction-required: 도구 0개 허용 (하한 제거)
        AgentBuilderPolicy.validate_tool_count(0)  # 예외 없음

    def test_validate_tool_count_over_max_raises(self):
        with pytest.raises(ValueError, match="최대"):
            AgentBuilderPolicy.validate_tool_count(6)

    # ── validate_worker_count ───────────────────────────────────

    def test_validate_worker_count_empty_passes(self):
        # agent-instruction-required: 워커 0개 허용 (하한 제거)
        AgentBuilderPolicy.validate_worker_count([])  # 예외 없음

    def test_validate_worker_count_over_max_raises(self):
        workers = [
            WorkerDefinition(
                tool_id=f"tool_{i}", worker_id=f"w_{i}", description="d",
            )
            for i in range(7)
        ]
        with pytest.raises(ValueError, match="최대"):
            AgentBuilderPolicy.validate_worker_count(workers)

    # ── validate_system_prompt ──────────────────────────────────

    def test_validate_system_prompt_normal_passes(self):
        AgentBuilderPolicy.validate_system_prompt("짧은 프롬프트")

    def test_validate_system_prompt_at_limit_passes(self):
        AgentBuilderPolicy.validate_system_prompt("a" * 4000)

    def test_validate_system_prompt_over_limit_raises(self):
        with pytest.raises(ValueError, match="4000"):
            AgentBuilderPolicy.validate_system_prompt("a" * 4001)

    def test_validate_system_prompt_empty_raises(self):
        # agent-instruction-required: 빈 지침 거부 (자동생성 제거)
        with pytest.raises(ValueError, match="비어"):
            AgentBuilderPolicy.validate_system_prompt("")

    def test_validate_system_prompt_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="비어"):
            AgentBuilderPolicy.validate_system_prompt("   \n\t  ")

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

    def test_validate_update_empty_system_prompt_raises(self):
        # agent-instruction-required: 빈 문자열은 '변경 안 함'(None)과 구분되어 거부
        with pytest.raises(ValueError, match="비어"):
            UpdateAgentPolicy.validate_update(status="active", system_prompt="")

    def test_validate_update_whitespace_system_prompt_raises(self):
        with pytest.raises(ValueError, match="비어"):
            UpdateAgentPolicy.validate_update(status="active", system_prompt="   ")
