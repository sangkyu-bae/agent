"""MockActionExecutor 단위 테스트.

approval-gate-phase2 D-06 — src 에서 tests/support 로 옮긴 테스트 더블.
"""
from unittest.mock import MagicMock

import pytest

from tests.support.approval.mock_executor import (
    FAILING_TOOL_ID,
    MockActionExecutor,
)


def _executor() -> tuple[MockActionExecutor, MagicMock]:
    logger = MagicMock()
    return MockActionExecutor(logger=logger), logger


class TestSupports:
    def test_모든_도구를_받는다(self):
        """테스트에서 어떤 tool_id 든 받는다."""
        ex, _ = _executor()
        assert ex.supports("email_send") is True
        assert ex.supports("rate_update") is True


class TestExecute:
    @pytest.mark.asyncio
    async def test_성공을_반환한다(self):
        ex, _ = _executor()
        result = await ex.execute(
            tool_id="email_send", tool_args={"to": "a@b.c"}, request_id="req1"
        )
        assert result.ok is True
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_산출물에_도구id가_담긴다(self):
        """재개 시 워커 결과로 주입되므로 무엇이 집행됐는지 드러나야 한다."""
        ex, _ = _executor()
        result = await ex.execute(
            tool_id="rate_update", tool_args={}, request_id="req1"
        )
        assert "rate_update" in result.output

    @pytest.mark.asyncio
    async def test_실제_부작용이_없음을_밝힌다(self):
        ex, _ = _executor()
        result = await ex.execute(tool_id="t", tool_args={}, request_id="req1")
        assert "mock" in result.output.lower()

    @pytest.mark.asyncio
    async def test_집행을_로그로_남긴다(self):
        ex, logger = _executor()
        await ex.execute(tool_id="t", tool_args={"a": 1}, request_id="req1")
        assert logger.info.called
        kwargs = logger.info.call_args.kwargs
        assert kwargs["request_id"] == "req1"
        assert kwargs["tool_id"] == "t"

    @pytest.mark.asyncio
    async def test_인자_값은_로그에_남기지_않는다(self):
        """초안·인자에 PII 가 담길 수 있어 키만 남긴다 (Design §7)."""
        ex, logger = _executor()
        await ex.execute(
            tool_id="t", tool_args={"email": "secret@x.com"}, request_id="req1"
        )
        assert logger.info.call_args.kwargs["arg_keys"] == ["email"]


class TestForcedFailure:
    @pytest.mark.asyncio
    async def test_예약_도구id는_실패를_반환한다(self):
        """집행 실패 → failed 경로를 E2E 로 검증하기 위한 통로."""
        ex, _ = _executor()
        result = await ex.execute(
            tool_id=FAILING_TOOL_ID, tool_args={}, request_id="req1"
        )
        assert result.ok is False
        assert result.error_message

    @pytest.mark.asyncio
    async def test_실패는_예외가_아니라_값으로_돌아온다(self):
        """FR-25 — 집행 실패는 정상 흐름의 한 갈래지 시스템 오류가 아니다."""
        ex, _ = _executor()
        result = await ex.execute(
            tool_id=FAILING_TOOL_ID, tool_args={}, request_id="req1"
        )
        assert result.ok is False  # 예외가 올라왔다면 여기 도달하지 못한다
