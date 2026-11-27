"""회차 스케줄러 — 30초 틱 1회의 일 (ticker 가 부른다).

Design Ref: stock-analysis-agents §2.2, DD6, Plan FR-01 · SC-2.
1. 설정 시각이 지난 슬롯마다 회차 행을 선점한다
(DB UNIQUE — 다중 인스턴스·다음 틱에서 1회만)
2. 스위치 OFF → skipped(DISABLED) 를 남기고 LLM 을 부르지 않는다 (SC-2)
3. 주말 → skipped(WEEKEND), 다른 회차 실행 중 → skipped(BUSY)
4. 아니면 회차를 백그라운드 태스크로 실행한다 — 틱은 막히지 않는다
기동 시 `recover()` 가 남아 있는 running 회차를 abandoned 로 회수한다 (§10, U11).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from datetime import datetime

from src.application.market_analysis.ports import RoundStore, SettingReader
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.round import RoundSchedulePolicy, SkipReason
from src.domain.market_analysis.value_objects import RoundKind, RoundTrigger


class RoundScheduler:
    def __init__(
        self,
        *,
        settings: SettingReader,
        rounds: RoundStore,
        runner: object,
        logger: LoggerInterface,
        now_utc: Callable[[], datetime],
    ) -> None:
        self._settings = settings
        self._rounds = rounds
        self._runner = runner
        self._logger = logger
        self._now_utc = now_utc
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def recover(self, request_id: str) -> int:
        count = await self._rounds.abandon_running(request_id)
        if count:
            self._logger.warning(
                "market_analysis abandoned running rounds on start",
                request_id=request_id,
                count=count,
            )
        return count

    async def tick(self, request_id: str) -> list[tuple[str, str]]:
        setting = await self._settings.get(request_id)
        actions: list[tuple[str, str]] = []
        for due in RoundSchedulePolicy.due_slots(self._now_utc(), setting.round_times):
            round_id = await self._rounds.try_claim(
                trade_date=due.trade_date,
                slot=due.slot,
                kind=due.kind,
                trigger=RoundTrigger.AUTO,
                request_id=request_id,
            )
            if round_id is None:
                continue  # 이미 다른 틱·인스턴스가 처리했다
            reason = await self._skip_reason(
                setting.enabled, due.trade_date, round_id, request_id
            )
            if reason is not None:
                await self._rounds.skip(
                    round_id=round_id, reason=reason, request_id=request_id
                )
                actions.append((due.slot, f"skipped:{reason}"))
                continue
            self._task = asyncio.create_task(
                self._runner.run(  # type: ignore[attr-defined]
                    round_id=round_id,
                    trade_date=due.trade_date,
                    kind=due.kind,
                    setting=setting,
                    request_id=request_id,
                ),
                name=f"market-analysis-round-{round_id}",
            )
            actions.append((due.slot, "started"))
        return actions

    async def run_now(self, kind: RoundKind | None, request_id: str) -> int | None:
        """수동 회차 (module-8 `POST /rounds/run-now`). 자동 스위치·주말과 무관하고
        상한·휴장 판정은 회차 실행기가 그대로 적용한다. 실행 중인 회차가 있거나
        같은 분에 이미 수동 회차가 있으면 None (호출자가 409).
        종류를 안 주면 자동 회차와 같은 규칙(서울 15:30 기준)으로 정한다."""
        if self.running or await self._rounds.any_running(
            exclude_id=None, request_id=request_id
        ):
            return None
        setting = await self._settings.get(request_id)
        now_kst = RoundSchedulePolicy.to_kst(self._now_utc())
        slot = now_kst.strftime("%H:%M")
        kind = kind or RoundSchedulePolicy.kind_for(slot)
        round_id = await self._rounds.try_claim(
            trade_date=now_kst.date(),
            slot=slot,
            kind=kind,
            trigger=RoundTrigger.MANUAL,
            request_id=request_id,
        )
        if round_id is None:
            return None
        self._task = asyncio.create_task(
            self._runner.run(  # type: ignore[attr-defined]
                round_id=round_id,
                trade_date=now_kst.date(),
                kind=kind,
                setting=setting,
                request_id=request_id,
            ),
            name=f"market-analysis-round-{round_id}",
        )
        return round_id

    async def _skip_reason(
        self, enabled: bool, trade_date, round_id: int, request_id: str
    ) -> SkipReason | None:
        if not enabled:
            return SkipReason.DISABLED
        if RoundSchedulePolicy.is_weekend(trade_date):
            return SkipReason.WEEKEND
        if self.running or await self._rounds.any_running(
            exclude_id=round_id, request_id=request_id
        ):
            return SkipReason.BUSY
        return None

    async def wait_idle(self) -> None:
        if self._task is not None:
            await self._task

    async def stop(self) -> None:
        """실행 중 회차를 취소한다. 남은
        running 행은 다음 기동의 recover 가 회수한다."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._task = None
