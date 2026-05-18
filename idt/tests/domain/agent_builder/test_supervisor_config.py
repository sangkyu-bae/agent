"""SupervisorConfig 단위 테스트."""
from src.domain.agent_builder.schemas import SupervisorConfig


class TestSupervisorConfig:
    def test_default_values(self):
        config = SupervisorConfig()
        assert config.max_iterations == 10
        assert config.token_limit == 8000
        assert config.quality_gate_enabled is False
        assert config.max_retries_per_worker == 2

    def test_custom_values(self):
        config = SupervisorConfig(
            max_iterations=5,
            token_limit=4000,
            quality_gate_enabled=True,
            max_retries_per_worker=3,
        )
        assert config.max_iterations == 5
        assert config.token_limit == 4000
        assert config.quality_gate_enabled is True
        assert config.max_retries_per_worker == 3

    def test_frozen(self):
        config = SupervisorConfig()
        try:
            config.max_iterations = 20
            assert False, "Should raise FrozenInstanceError"
        except AttributeError:
            pass
