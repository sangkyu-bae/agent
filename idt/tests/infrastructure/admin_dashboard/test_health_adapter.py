"""StorageHealthAdapter 테스트 — ok/fail/timeout 격리 + 병렬 실행 (Design D5, §5.1)."""
import asyncio
import time
from unittest.mock import MagicMock

import pytest

from src.infrastructure.admin_dashboard.health_adapter import StorageHealthAdapter


def _adapter(checks, timeout_seconds: float = 3.0) -> StorageHealthAdapter:
    return StorageHealthAdapter(
        checks=checks, logger=MagicMock(), timeout_seconds=timeout_seconds
    )


class TestStorageHealthAdapter:
    @pytest.mark.asyncio
    async def test_all_ok(self):
        async def ok() -> None:
            return None

        adapter = _adapter({"mysql": ok, "qdrant": ok})
        components = await adapter.check_all()

        assert [c.name for c in components] == ["mysql", "qdrant"]
        assert all(c.status == "ok" for c in components)
        assert all(c.latency_ms is not None and c.latency_ms >= 0 for c in components)
        assert all(c.error is None for c in components)

    @pytest.mark.asyncio
    async def test_single_failure_is_isolated(self):
        async def ok() -> None:
            return None

        async def boom() -> None:
            raise ConnectionError("connection refused")

        adapter = _adapter({"mysql": ok, "elasticsearch": boom})
        components = await adapter.check_all()

        by_name = {c.name: c for c in components}
        assert by_name["mysql"].status == "ok"
        assert by_name["elasticsearch"].status == "fail"
        assert "connection refused" in by_name["elasticsearch"].error

    @pytest.mark.asyncio
    async def test_timeout_becomes_fail(self):
        async def slow() -> None:
            await asyncio.sleep(1.0)

        adapter = _adapter({"qdrant": slow}, timeout_seconds=0.05)
        components = await adapter.check_all()

        assert components[0].status == "fail"
        assert "timeout" in components[0].error

    @pytest.mark.asyncio
    async def test_checks_run_in_parallel(self):
        async def sleepy() -> None:
            await asyncio.sleep(0.2)

        adapter = _adapter({"a": sleepy, "b": sleepy, "c": sleepy})
        start = time.monotonic()
        await adapter.check_all()
        elapsed = time.monotonic() - start

        # 직렬이면 0.6s 이상 — 병렬이면 ~0.2s (여유 0.5s)
        assert elapsed < 0.5

    @pytest.mark.asyncio
    async def test_error_without_message_uses_type_name(self):
        async def boom() -> None:
            raise RuntimeError()

        adapter = _adapter({"mysql": boom})
        components = await adapter.check_all()

        assert components[0].status == "fail"
        assert components[0].error == "RuntimeError"
