"""domain/middleware_agent/policies 단위 테스트 (mock 금지)."""
import pytest

from src.domain.middleware_agent.policies import MiddlewareAgentPolicy
from src.domain.middleware_agent.schemas import MiddlewareConfig, MiddlewareType


def _cfg(t: MiddlewareType, order: int = 0) -> MiddlewareConfig:
    return MiddlewareConfig(middleware_type=t, config={}, sort_order=order)


class TestValidateToolCount:
    def test_one_tool_passes(self):
        MiddlewareAgentPolicy.validate_tool_count(["tool_a"])

    def test_five_tools_passes(self):
        MiddlewareAgentPolicy.validate_tool_count(["a", "b", "c", "d", "e"])

    def test_zero_tools_raises(self):
        with pytest.raises(ValueError, match="tool_ids"):
            MiddlewareAgentPolicy.validate_tool_count([])

    def test_six_tools_raises(self):
        with pytest.raises(ValueError):
            MiddlewareAgentPolicy.validate_tool_count(["a", "b", "c", "d", "e", "f"])


class TestValidateMiddlewareCount:
    def test_zero_middlewares_passes(self):
        MiddlewareAgentPolicy.validate_middleware_count([])

    def test_five_middlewares_passes(self):
        cfgs = [_cfg(t) for t in MiddlewareType]
        MiddlewareAgentPolicy.validate_middleware_count(cfgs)

    def test_six_middlewares_raises(self):
        cfgs = [_cfg(MiddlewareType.PII)] * 6
        with pytest.raises(ValueError):
            MiddlewareAgentPolicy.validate_middleware_count(cfgs)


class TestValidateMiddlewareCombination:
    def test_unique_types_passes(self):
        cfgs = [
            _cfg(MiddlewareType.PII),
            _cfg(MiddlewareType.SUMMARIZATION),
            _cfg(MiddlewareType.TOOL_RETRY),
        ]
        MiddlewareAgentPolicy.validate_middleware_combination(cfgs)

    def test_duplicate_type_raises(self):
        cfgs = [_cfg(MiddlewareType.PII), _cfg(MiddlewareType.PII)]
        with pytest.raises(ValueError, match="Duplicate"):
            MiddlewareAgentPolicy.validate_middleware_combination(cfgs)

    def test_empty_list_passes(self):
        MiddlewareAgentPolicy.validate_middleware_combination([])


class TestValidateSystemPrompt:
    def test_valid_prompt_passes(self):
        MiddlewareAgentPolicy.validate_system_prompt("you are helpful")

    def test_empty_prompt_passes(self):
        MiddlewareAgentPolicy.validate_system_prompt("")

    def test_exact_limit_passes(self):
        MiddlewareAgentPolicy.validate_system_prompt("a" * 4000)

    def test_over_limit_raises(self):
        with pytest.raises(ValueError, match="4000"):
            MiddlewareAgentPolicy.validate_system_prompt("a" * 4001)
