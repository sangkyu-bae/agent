"""config.agent_timezone (runtime-datetime-context D11)."""
from src.config import Settings


def test_default_agent_timezone_is_asia_seoul():
    assert Settings(_env_file=None).agent_timezone == "Asia/Seoul"


def test_agent_timezone_env_override(monkeypatch):
    monkeypatch.setenv("AGENT_TIMEZONE", "UTC")
    assert Settings(_env_file=None).agent_timezone == "UTC"
