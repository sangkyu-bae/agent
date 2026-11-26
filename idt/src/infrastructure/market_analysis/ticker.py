"""회차 틱 루프 — lifespan 백그라운드 태스크.

Design Ref: stock-analysis-agents
DD6 — 플랫폼 워커에는 비에이전트 주기 작업 등록 체계가 없어
모듈이 자기 루프를 갖는다(분리할 때 그대로 옮긴다).
- 시작 시 1회 recover(running 회차 회수), 이후 interval 마다 tick
- tick 예외는 기록만 하고 루프는 계속 돈다
- stop: 루프를 멈추고 스케줄러의 실행 중 회차를 취소한다 (다음 기동의 recover 가 회수)
- application 을 import 하지 않는다 (scheduler 는 recover·tick·stop 을 가진 객체면 된다)
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any

from src.domain.logging.interfaces.logger_interface import LoggerInterface


class MarketAnalysisTicker:
    def __init__(
        self, scheduler: Any, *, interval_sec: float, logger: LoggerInterface
    ) -> None:
        self._scheduler = scheduler
        self._interval = interval_sec
        self._logger = logger
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.running:
            return
        self._task = asyncio.create_task(self._loop(), name="market-analysis-ticker")
        self._logger.info("market_analysis ticker started", interval_sec=self._interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
            await self._scheduler.stop()
            self._logger.info("market_analysis ticker stopped")

    async def _loop(self) -> None:
        try:
            await self._scheduler.recover(f"ma-recover-{uuid.uuid4().hex[:8]}")
        except Exception as e:  # noqa: BLE001 — 회수 실패가 루프를 막지 않는다
            self._logger.error("market_analysis recover failed", exception=e)
        while True:
            request_id = f"ma-tick-{uuid.uuid4().hex[:8]}"
            try:
                await self._scheduler.tick(request_id)
            except Exception as e:  # noqa: BLE001 — 틱 하나의 실패가 루프를 멈추면 안 된다
                self._logger.error(
                    "market_analysis tick failed", exception=e, request_id=request_id
                )
            await asyncio.sleep(self._interval)
