"""CachedGraphSettingsReader — 요청 세션 밖(검색·노출 판단)에서 설정 읽기.

Design Ref: graph-rag-foundation §10.1 — TTL 30초 캐시, PUT·단계 변경 시 즉시 무효화.
읽기 실패는 닫힌 기본값(off)을 돌려주고 캐시하지 않는다(다음 호출에서 재시도).
앱 수명 싱글턴 — 호출마다 짧은 세션을 연다(SessionScoped 저장소 선례).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from src.domain.graph_rag.interfaces import (
    GraphRagSettingsRepositoryPort,
    GraphSettingsReaderPort,
)
from src.domain.graph_rag.value_objects import GraphRagSettings
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_REQUEST_ID = "graph-settings-reader"


class CachedGraphSettingsReader(GraphSettingsReaderPort):
    def __init__(
        self,
        *,
        session_scope: Callable[[], AbstractAsyncContextManager[Any]],
        repo_factory: Callable[[Any], GraphRagSettingsRepositoryPort],
        logger: LoggerInterface,
        ttl_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_scope = session_scope
        self._repo_factory = repo_factory
        self._logger = logger
        self._ttl = ttl_seconds
        self._clock = clock
        self._cached: GraphRagSettings | None = None
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        self._cached = None

    async def get(self) -> GraphRagSettings:
        if self._fresh():
            return self._cached  # type: ignore[return-value]
        async with self._lock:
            if self._fresh():
                return self._cached  # type: ignore[return-value]
            try:
                async with self._session_scope() as session:
                    settings = await self._repo_factory(session).get(_REQUEST_ID)
            except Exception as e:  # noqa: BLE001 — 실패는 닫힌 기본값
                self._logger.warning(
                    "graph settings read failed — using closed defaults", exception=e
                )
                return GraphRagSettings.defaults()
            self._cached = settings
            self._loaded_at = self._clock()
            return settings

    def _fresh(self) -> bool:
        return self._cached is not None and self._clock() - self._loaded_at < self._ttl
