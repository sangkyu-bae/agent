"""domain/middleware_agent/schemas 단위 테스트 (mock 금지)."""
from datetime import datetime
import pytest

from src.domain.middleware_agent.schemas import (
    MiddlewareAgentDefinition,
    MiddlewareConfig,
    MiddlewareType,
)


class TestMiddlewareType:
    def test_all_supported_types_exist(self):
        assert MiddlewareType.SUMMARIZATION.value == "summarization"
        assert MiddlewareType.PII.value == "pii"
        assert MiddlewareType.TOOL_RETRY.value == "tool_retry"
        assert MiddlewareType.MODEL_CALL_LIMIT.value == "model_call_limit"
        assert MiddlewareType.MODEL_FALLBACK.value == "model_fallback"

    def test_from_string_value(self):
        assert MiddlewareType("summarization") == MiddlewareType.SUMMARIZATION
        assert MiddlewareType("pii") == MiddlewareType.PII

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError):
            MiddlewareType("unknown_type")


class TestMiddlewareConfig:
    def test_create_with_required_fields(self):
        cfg = MiddlewareConfig(
            middleware_type=MiddlewareType.SUMMARIZATION,
            config={"trigger": ("tokens", 4000)},
        )
        assert cfg.middleware_type == MiddlewareType.SUMMARIZATION
        assert cfg.sort_order == 0

    def test_default_sort_order_is_zero(self):
        cfg = MiddlewareConfig(
            middleware_type=MiddlewareType.PII,
            config={"pii_type": "email"},
        )
        assert cfg.sort_order == 0

    def test_custom_sort_order(self):
        cfg = MiddlewareConfig(
            middleware_type=MiddlewareType.TOOL_RETRY,
            config={},
            sort_order=2,
        )
        assert cfg.sort_order == 2

    def test_is_frozen(self):
        cfg = MiddlewareConfig(middleware_type=MiddlewareType.PII, config={})
        with pytest.raises((AttributeError, TypeError)):
            cfg.sort_order = 99  # type: ignore


class TestMiddlewareAgentDefinition:
    def _make_agent(self, **kwargs) -> MiddlewareAgentDefinition:
        now = datetime(2026, 3, 24, 0, 0, 0)
        defaults = dict(
            id="agent-uuid-1",
            user_id="user-1",
            name="테스트 에이전트",
            description="desc",
            system_prompt="you are a helpful assistant",
            model_name="gpt-4o",
            tool_ids=["internal_document_search"],
            middleware_configs=[],
            status="active",
            created_at=now,
            updated_at=now,
        )
        defaults.update(kwargs)
        return MiddlewareAgentDefinition(**defaults)

    def test_create_basic_agent(self):
        agent = self._make_agent()
        assert agent.id == "agent-uuid-1"
        assert agent.status == "active"

    def test_sorted_middleware_by_sort_order(self):
        cfg_a = MiddlewareConfig(MiddlewareType.PII, {}, sort_order=2)
        cfg_b = MiddlewareConfig(MiddlewareType.SUMMARIZATION, {}, sort_order=0)
        cfg_c = MiddlewareConfig(MiddlewareType.TOOL_RETRY, {}, sort_order=1)
        agent = self._make_agent(middleware_configs=[cfg_a, cfg_b, cfg_c])

        sorted_mw = agent.sorted_middleware()
        assert sorted_mw[0].middleware_type == MiddlewareType.SUMMARIZATION
        assert sorted_mw[1].middleware_type == MiddlewareType.TOOL_RETRY
        assert sorted_mw[2].middleware_type == MiddlewareType.PII

    def test_apply_update_system_prompt(self):
        agent = self._make_agent()
        agent.apply_update(system_prompt="new prompt", name=None, middleware_configs=None)
        assert agent.system_prompt == "new prompt"
        assert agent.name == "테스트 에이전트"  # 변경 없음

    def test_apply_update_name(self):
        agent = self._make_agent()
        agent.apply_update(system_prompt=None, name="새 이름", middleware_configs=None)
        assert agent.name == "새 이름"

    def test_apply_update_middleware_configs(self):
        agent = self._make_agent()
        new_configs = [MiddlewareConfig(MiddlewareType.PII, {"pii_type": "email"})]
        agent.apply_update(system_prompt=None, name=None, middleware_configs=new_configs)
        assert len(agent.middleware_configs) == 1

    def test_apply_update_none_values_no_change(self):
        agent = self._make_agent()
        original_prompt = agent.system_prompt
        agent.apply_update(system_prompt=None, name=None, middleware_configs=None)
        assert agent.system_prompt == original_prompt

    def test_sorted_middleware_empty(self):
        agent = self._make_agent(middleware_configs=[])
        assert agent.sorted_middleware() == []
