"""ApprovalExecutionConfig 단위 테스트.

Design Ref: approval-gate-phase2-mcp-executor §10.3.
"""
import pytest
from pydantic import ValidationError

from src.infrastructure.config.approval_execution_config import (
    ApprovalExecutionConfig,
)

_ENV_NAMES = (
    "APPROVAL_EXEC_CONNECT_TIMEOUT",
    "APPROVAL_EXEC_TOTAL_TIMEOUT",
    "APPROVAL_EXEC_OUTPUT_MAX_CHARS",
)


class TestDefaults:
    def test_기본값(self, monkeypatch):
        for name in _ENV_NAMES:
            monkeypatch.delenv(name, raising=False)
        config = ApprovalExecutionConfig(_env_file=None)
        assert config.APPROVAL_EXEC_CONNECT_TIMEOUT == 15.0
        assert config.APPROVAL_EXEC_TOTAL_TIMEOUT == 60.0
        assert config.APPROVAL_EXEC_OUTPUT_MAX_CHARS == 8000


class TestGetTimeout:
    def test_read는_total에_맞춘다(self, monkeypatch):
        monkeypatch.setenv("APPROVAL_EXEC_CONNECT_TIMEOUT", "5")
        monkeypatch.setenv("APPROVAL_EXEC_TOTAL_TIMEOUT", "30")
        timeout = ApprovalExecutionConfig(_env_file=None).get_timeout()
        assert timeout.connect == 5
        assert timeout.read == 30
        assert timeout.total == 30

    def test_0_이하는_거부한다(self, monkeypatch):
        monkeypatch.setenv("APPROVAL_EXEC_TOTAL_TIMEOUT", "0")
        with pytest.raises(ValidationError):
            ApprovalExecutionConfig(_env_file=None)
