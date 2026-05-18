"""SupervisorHooks 단위 테스트 (TC-11~12)."""
from src.application.agent_builder.supervisor_hooks import DefaultHooks


def _make_state(**overrides) -> dict:
    base = {
        "messages": [],
        "iteration_count": 0,
        "max_iterations": 10,
        "token_usage": 0,
        "token_limit": 8000,
        "next_worker": "",
        "last_worker_id": "",
        "available_workers": ["worker_0", "worker_1"],
        "quality_gate_enabled": False,
        "retry_counts": {},
        "max_retries_per_worker": 2,
        "forced_worker": "",
        "skipped_workers": [],
    }
    base.update(overrides)
    return base


class TestDefaultHooks:
    def test_force_worker_returns_none(self):
        """TC-11 기본: DefaultHooks는 강제 워커 없음."""
        hooks = DefaultHooks()
        state = _make_state()
        assert hooks.force_worker(state) is None

    def test_skip_workers_returns_empty(self):
        """TC-12 기본: DefaultHooks는 스킵 워커 없음."""
        hooks = DefaultHooks()
        state = _make_state()
        assert hooks.skip_workers(state) == []


class TestCustomHooks:
    def test_force_worker_override(self):
        """TC-11: force_worker 반환 시 해당 워커 직행."""

        class ForceFirstHooks:
            def force_worker(self, state):
                return "worker_0"

            def skip_workers(self, state):
                return []

        hooks = ForceFirstHooks()
        state = _make_state()
        assert hooks.force_worker(state) == "worker_0"

    def test_skip_workers_override(self):
        """TC-12: skip_workers에 포함된 워커는 스킵."""

        class SkipFirstHooks:
            def force_worker(self, state):
                return None

            def skip_workers(self, state):
                return ["worker_0"]

        hooks = SkipFirstHooks()
        state = _make_state()
        assert hooks.skip_workers(state) == ["worker_0"]
