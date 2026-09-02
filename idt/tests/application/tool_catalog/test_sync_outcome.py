"""SyncOutcome / _hint_for 테스트 — MCP 도구 동기화 시도 결과 값 객체.

Design Ref: mcp-tool-auto-sync §3.1, §6.2
"""
import pytest

from src.application.tool_catalog.sync_outcome import (
    DEFAULT_SYNC_HINT,
    SyncOutcome,
    hint_for,
)


class TestSyncOutcome:
    def test_skipped_marks_not_attempted(self):
        """FR-06: sync 의존성 미주입 — 시도조차 하지 않았음을 구분한다."""
        outcome = SyncOutcome.skipped()

        assert outcome.attempted is False
        assert outcome.ok is False
        assert outcome.synced_count == 0
        assert outcome.error_hint is None

    def test_succeeded_carries_count(self):
        outcome = SyncOutcome.succeeded(3)

        assert outcome.attempted is True
        assert outcome.ok is True
        assert outcome.synced_count == 3
        assert outcome.error_hint is None

    def test_failed_carries_hint_and_zero_count(self):
        outcome = SyncOutcome.failed("연결 실패")

        assert outcome.attempted is True
        assert outcome.ok is False
        assert outcome.synced_count == 0
        assert outcome.error_hint == "연결 실패"

    def test_is_frozen(self):
        """값 객체이므로 변경 불가."""
        outcome = SyncOutcome.succeeded(1)
        with pytest.raises(Exception):
            outcome.ok = False  # type: ignore[misc]


class TestHintFor:
    def test_session_terminated_maps_to_api_key_hint(self):
        """TOOL-MCP-001 §3: 'Session terminated'는 대부분 api_key 누락 404다."""
        hint = hint_for(RuntimeError("Session terminated"))

        assert "api_key" in hint
        assert "404" in hint

    def test_session_terminated_is_case_insensitive(self):
        assert hint_for(RuntimeError("SESSION TERMINATED")) == hint_for(
            RuntimeError("session terminated")
        )

    def test_timeout_maps_to_delay_hint(self):
        import asyncio

        hint = hint_for(asyncio.TimeoutError())

        assert "지연" in hint or "응답" in hint

    @pytest.mark.parametrize(
        "message,expected_code",
        [("HTTP 404 Not Found", "404"), ("401 Unauthorized", "401"), ("403 Forbidden", "403")],
    )
    def test_http_status_codes_map_to_specific_hints(self, message, expected_code):
        hint = hint_for(RuntimeError(message))

        assert expected_code in hint
        assert hint != DEFAULT_SYNC_HINT

    def test_unknown_error_falls_back_to_default(self):
        hint = hint_for(RuntimeError("무언가 알 수 없는 실패"))

        assert hint == DEFAULT_SYNC_HINT

    def test_hint_never_leaks_raw_exception_message(self):
        """§7 보안: 원본 예외(내부 URL·헤더 포함 가능)를 그대로 노출하지 않는다."""
        secret = "https://internal.example.com/mcp?api_key=SECRET123"
        hint = hint_for(RuntimeError(secret))

        assert "SECRET123" not in hint
        assert "internal.example.com" not in hint

    def test_hint_for_timeout_error_class_without_message(self):
        """asyncio.TimeoutError는 str()이 빈 문자열이라 클래스명으로도 판별해야 한다."""
        import asyncio

        exc = asyncio.TimeoutError()
        assert str(exc) == ""
        assert hint_for(exc) != DEFAULT_SYNC_HINT


class TestRunToolSyncRedaction:
    """§7 보안 미결 항목: 로그에 남는 예외 메시지의 시크릿 마스킹."""

    @pytest.mark.asyncio
    async def test_api_key_in_error_message_is_masked_in_log(self):
        from unittest.mock import AsyncMock, MagicMock

        from src.application.tool_catalog.sync_outcome import run_tool_sync

        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(
            side_effect=RuntimeError(
                "GET https://server.smithery.ai/x/mcp?api_key=SECRET123&p=1 failed"
            )
        )
        logger = MagicMock()

        outcome = await run_tool_sync(sync_uc, "srv-1", "req-1", 10.0, logger)

        logged = logger.warning.call_args.kwargs["error"]
        assert "SECRET123" not in logged
        assert "api_key=***" in logged
        assert "p=1" in logged  # 비밀이 아닌 파라미터는 보존
        assert outcome.ok is False

    @pytest.mark.asyncio
    async def test_token_and_secret_params_are_masked(self):
        from unittest.mock import AsyncMock, MagicMock

        from src.application.tool_catalog.sync_outcome import run_tool_sync

        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(
            side_effect=RuntimeError("url?token=AAA&secret=BBB&password=CCC")
        )
        logger = MagicMock()

        await run_tool_sync(sync_uc, "srv-1", "req-1", 10.0, logger)

        logged = logger.warning.call_args.kwargs["error"]
        for leaked in ("AAA", "BBB", "CCC"):
            assert leaked not in logged

    @pytest.mark.asyncio
    async def test_none_sync_use_case_returns_skipped(self):
        from unittest.mock import MagicMock

        from src.application.tool_catalog.sync_outcome import run_tool_sync

        outcome = await run_tool_sync(None, "srv-1", "req-1", 10.0, MagicMock())

        assert outcome.attempted is False
