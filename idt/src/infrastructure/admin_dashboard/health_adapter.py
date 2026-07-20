"""저장소 헬스체크 어댑터 — MySQL/Qdrant/ES 병렬 ping (Design D5).

- 컴포넌트별 asyncio.wait_for 타임아웃으로 격리 — 1개 다운이 전체를 막지 않음.
- 실패는 예외 전파 대신 HealthComponent(status="fail")로 변환 (HTTP 200 유지).
"""
import asyncio
import time
from typing import Awaitable, Callable

from qdrant_client import AsyncQdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.domain.admin_dashboard.interfaces import StorageHealthPort
from src.domain.admin_dashboard.schemas import HealthComponent
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.elasticsearch.es_client import ElasticsearchClient

HealthCheck = Callable[[], Awaitable[None]]


class StorageHealthAdapter(StorageHealthPort):
    def __init__(
        self,
        checks: dict[str, HealthCheck],
        logger: LoggerInterface,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._checks = checks
        self._logger = logger
        self._timeout = timeout_seconds

    async def check_all(self) -> list[HealthComponent]:
        results = await asyncio.gather(
            *(self._check_one(name, check) for name, check in self._checks.items())
        )
        return list(results)

    async def _check_one(self, name: str, check: HealthCheck) -> HealthComponent:
        start = time.monotonic()
        try:
            await asyncio.wait_for(check(), timeout=self._timeout)
        except asyncio.TimeoutError:
            self._logger.warning(
                "storage health check timeout",
                component=name,
                timeout_seconds=self._timeout,
            )
            return HealthComponent(
                name=name,
                status="fail",
                latency_ms=None,
                error=f"timeout({self._timeout:g}s)",
            )
        except Exception as e:
            self._logger.warning(
                "storage health check failed", component=name, error=str(e)
            )
            return HealthComponent(
                name=name,
                status="fail",
                latency_ms=None,
                error=str(e) or type(e).__name__,
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        return HealthComponent(
            name=name, status="ok", latency_ms=latency_ms, error=None
        )


def build_mysql_check(engine: AsyncEngine) -> HealthCheck:
    async def _check() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    return _check


def build_qdrant_check(client: AsyncQdrantClient) -> HealthCheck:
    async def _check() -> None:
        await client.get_collections()

    return _check


def build_es_check(es_client: ElasticsearchClient) -> HealthCheck:
    async def _check() -> None:
        ok = await es_client.get_client().ping()
        if not ok:
            raise ConnectionError("elasticsearch ping returned false")

    return _check
