"""stock-analysis-agents 조립 — 코어에 끼우는 단일 지점.

Design Ref: stock-analysis-agents §2.1, §15, DD6. firewall_admin_di 선례를 따른다.
main.py 는 이 파일의 `wire_market_analysis` ·
`start_market_analysis` · `close_market_analysis`
· `MarketAnalysisPlatform` 만 안다
(tests/contracts/test_market_analysis_isolation.py I2).

- MARKET_ANALYSIS_ENABLED=false(기본) →
조립하지 않음, 라우터 미등록(404), 플랫폼 의존성도 만들지 않음
- 켜져 있으면 main 이 넘긴 platform_factory
로 플랫폼 의존성을 받아 어댑터·파이프라인·회차를 조립
- MARKET_ANALYSIS_TICKER_ENABLED=false
→ 회차 실행기를 시작하지 않는다(조회·관리 API 는 동작)
- 조립 실패 → warning 1회 후 그 부분만 없음. 앱 기동은 계속된다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes import market_analysis_router
from src.application.market_analysis.access import GetAccessUseCase
from src.application.market_analysis.bootstrap_agents import BootstrapAgentsUseCase
from src.application.market_analysis.commands import (
    RunNowUseCase,
    SetEnabledUseCase,
    SetRoleAgentsUseCase,
    UpdateSettingsUseCase,
)
from src.application.market_analysis.index_chart import IndexChartService
from src.application.market_analysis.journal import JournalWriter
from src.application.market_analysis.judgement import BuyJudgement
from src.application.market_analysis.performance import PerformanceRecorder
from src.application.market_analysis.pipeline import StockAnalysisPipeline
from src.application.market_analysis.positions import PositionManager
from src.application.market_analysis.principles import SetPrincipleActiveUseCase
from src.application.market_analysis.queries import MarketAnalysisQueries
from src.application.market_analysis.regime import MarketRegimeService
from src.application.market_analysis.round_runner import RoundRunner
from src.application.market_analysis.scheduler import RoundScheduler
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.blueprint.llm.structured import StructuredCaller
from src.infrastructure.logging import StructuredLogger
from src.infrastructure.market_analysis.account_repository import (
    DecisionRepository,
    PositionRepository,
    RegimeRepository,
)
from src.infrastructure.market_analysis.adapters.access import PermissionCodesReader
from src.infrastructure.market_analysis.adapters.agent_creator import (
    PlatformAgentCreator,
)
from src.infrastructure.market_analysis.adapters.agent_runner import PlatformAgentRunner
from src.infrastructure.market_analysis.adapters.market_tools import PlatformMarketTools
from src.infrastructure.market_analysis.adapters.references import (
    PlatformReferenceChecker,
)
from src.infrastructure.market_analysis.adapters.structured import (
    PlatformStructuredExtractor,
)
from src.infrastructure.market_analysis.index_daily_repository import (
    IndexDailyRepository,
)
from src.infrastructure.market_analysis.journal_repository import (
    JournalRepository,
    PrincipleRepository,
)
from src.infrastructure.market_analysis.query_repository import QueryRepository
from src.infrastructure.market_analysis.report_repository import (
    ReportRepository,
    RoleAgentRepository,
)
from src.infrastructure.market_analysis.repositories import SessionSettingWriter
from src.infrastructure.market_analysis.round_repository import (
    RoundRepository,
    SessionSettingReader,
)
from src.infrastructure.market_analysis.ticker import MarketAnalysisTicker
from src.infrastructure.permission.repository import PermissionRepository
from src.infrastructure.persistence.database import get_session

TICK_SEC = 30.0


@dataclass(frozen=True)
class MarketAnalysisParts:
    ticker_enabled: bool
    logger: LoggerInterface


@dataclass(frozen=True)
class MarketAnalysisPlatform:
    """main.py 가 넘기는 플랫폼 의존성 — 모듈이
    켜졌을 때만 만들어진다 (platform_factory)."""

    session_factory: Callable[[], Any]
    run_agent_uc_builder: Callable[[Any], Any]
    create_agent_uc_builder: Callable[[Any], Any]
    auth_ctx_assembler: Callable[[str, str], Awaitable[Any]]
    mcp_server_finder: Callable[[str, str], Awaitable[Any]]
    mcp_client_factory: Callable[[Any, str, str], Any]
    news_search: Callable[..., str]
    utility_llm_provider: Any


@dataclass(frozen=True)
class MarketAnalysisRuntime:
    pipeline: StockAnalysisPipeline
    round_runner: RoundRunner
    scheduler: RoundScheduler
    ticker: MarketAnalysisTicker
    bootstrap: BootstrapAgentsUseCase
    extractor: PlatformStructuredExtractor
    journal_writer: JournalWriter
    set_principle_active: SetPrincipleActiveUseCase
    queries: MarketAnalysisQueries
    settings: SessionSettingReader
    roles: RoleAgentRepository
    update_settings: UpdateSettingsUseCase
    set_enabled: SetEnabledUseCase
    set_role_agents: SetRoleAgentsUseCase
    run_now: RunNowUseCase
    index_chart: IndexChartService


_parts: MarketAnalysisParts | None = None
_built = False
_runtime: MarketAnalysisRuntime | None = None
_ticker_wanted = False


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def build_market_analysis(
    settings: Any, logger: LoggerInterface
) -> MarketAnalysisParts | None:
    """설정 → 부품. 소비: config.market_analysis_enabled
    · market_analysis_ticker_enabled."""
    if not settings.market_analysis_enabled:
        return None
    try:
        parts = MarketAnalysisParts(
            ticker_enabled=bool(settings.market_analysis_ticker_enabled), logger=logger
        )
        logger.info("market_analysis enabled", ticker_enabled=parts.ticker_enabled)
        return parts
    except Exception as e:  # noqa: BLE001 — 부가 기능 조립 실패가 기동을 막으면 안 된다
        logger.warning(
            "market_analysis assembly failed — feature disabled", exception=e
        )
        return None


def build_runtime(
    platform: MarketAnalysisPlatform, logger: LoggerInterface
) -> MarketAnalysisRuntime:
    """어댑터 → 파이프라인 → 회차 → 스케줄러 → 틱. 네트워크는 타지 않는다."""
    sf = platform.session_factory
    tools = PlatformMarketTools(
        server_finder=platform.mcp_server_finder,
        client_factory=platform.mcp_client_factory,
        news_search=platform.news_search,
        logger=logger,
    )
    runner = PlatformAgentRunner(
        session_factory=sf,
        run_uc_builder=platform.run_agent_uc_builder,
        auth_ctx_assembler=platform.auth_ctx_assembler,
        logger=logger,
    )
    roles = RoleAgentRepository(sf, logger)
    settings_reader = SessionSettingReader(sf, logger)
    pipeline = StockAnalysisPipeline(
        tools=tools,
        runner=runner,
        reports=ReportRepository(sf, logger),
        roles=roles,
        logger=logger,
    )
    rounds = RoundRepository(sf, logger)
    extractor = PlatformStructuredExtractor(
        provider=platform.utility_llm_provider,
        caller_factory=lambda llm: StructuredCaller(llm, logger),
        logger=logger,
    )
    # module-6 가상 계좌 + module-7 원칙 주입(SC-5)·청산 저널(on_closed)
    positions = PositionRepository(sf, logger)
    decisions = DecisionRepository(sf, logger)
    regimes = RegimeRepository(sf, logger)
    principles = PrincipleRepository(sf, logger)
    journal_writer = JournalWriter(
        tools=tools,
        runner=runner,
        roles=roles,
        journals=JournalRepository(sf, logger),
        principles=principles,
        settings=settings_reader,
        extractor=extractor,
        logger=logger,
        now_utc=_utcnow,
    )
    judge_deps = dict(
        tools=tools,
        runner=runner,
        roles=roles,
        positions=positions,
        decisions=decisions,
        extractor=extractor,
        principles=principles,
        logger=logger,
        now_utc=_utcnow,
    )
    round_runner = RoundRunner(
        tools=tools,
        pipeline=pipeline,
        rounds=rounds,
        held=positions,
        logger=logger,
        now_utc=_utcnow,
        after_report=BuyJudgement(**judge_deps),
        market=MarketRegimeService(tools=tools, regimes=regimes, logger=logger),
        positions=PositionManager(**judge_deps, on_closed=journal_writer),
        performance=PerformanceRecorder(
            positions=positions, regimes=regimes, logger=logger
        ),
        roles=roles,
    )
    setting_writer = SessionSettingWriter(sf, logger)
    checker = PlatformReferenceChecker(
        session_factory=sf,
        server_finder=platform.mcp_server_finder,
        auth_ctx_assembler=platform.auth_ctx_assembler,
        logger=logger,
    )
    scheduler = RoundScheduler(
        settings=settings_reader,
        rounds=rounds,
        runner=round_runner,
        logger=logger,
        now_utc=_utcnow,
    )
    return MarketAnalysisRuntime(
        pipeline=pipeline,
        round_runner=round_runner,
        scheduler=scheduler,
        ticker=MarketAnalysisTicker(scheduler, interval_sec=TICK_SEC, logger=logger),
        bootstrap=BootstrapAgentsUseCase(
            roles=roles,
            creator=PlatformAgentCreator(
                session_factory=sf,
                create_uc_builder=platform.create_agent_uc_builder,
                viewer_role="user",
                logger=logger,
            ),
            settings=settings_reader,
            logger=logger,
        ),
        extractor=extractor,
        journal_writer=journal_writer,
        set_principle_active=SetPrincipleActiveUseCase(
            principles=principles, logger=logger
        ),
        # module-8 조회·설정·운영
        queries=MarketAnalysisQueries(
            store=QueryRepository(sf, logger),
            settings=settings_reader,
            now_utc=_utcnow,
            tools=tools,
            logger=logger,
        ),
        settings=settings_reader,
        roles=roles,
        update_settings=UpdateSettingsUseCase(
            reader=settings_reader,
            writer=setting_writer,
            checker=checker,
            logger=logger,
        ),
        set_enabled=SetEnabledUseCase(
            reader=settings_reader, writer=setting_writer, logger=logger
        ),
        set_role_agents=SetRoleAgentsUseCase(
            roles=roles, checker=checker, logger=logger
        ),
        run_now=RunNowUseCase(scheduler=scheduler, logger=logger),
        # market-index-ytd-chart §2.1 — 조회 때 꼬리 적재
        index_chart=IndexChartService(
            settings=settings_reader,
            store=IndexDailyRepository(sf, logger),
            tools=tools,
            logger=logger,
            now_utc=_utcnow,
        ),
    )


def get_market_analysis_api() -> MarketAnalysisRuntime | None:
    """라우터의 get_market_analysis_api 를 덮어쓴다. 런타임 조립에 실패했으면 None
    → 라우터가 503 MA_UNAVAILABLE."""
    return _runtime


def get_market_analysis() -> MarketAnalysisParts | None:
    """앱 수명 1회 조립 — 요청마다 재시도하지 않는다."""
    global _parts, _built
    if not _built:
        from src.config import settings

        _built = True
        _parts = build_market_analysis(settings, StructuredLogger("market_analysis"))
    return _parts


def get_runtime() -> MarketAnalysisRuntime | None:
    return _runtime


def wire_market_analysis(
    app: FastAPI,
    platform_factory: Callable[[], MarketAnalysisPlatform] | None = None,
) -> bool:
    """시장 분석 라우터 등록 + 런타임 조립. 꺼져
    있으면 아무것도 만들지 않는다(전 경로 404)."""
    global _runtime, _ticker_wanted
    parts = get_market_analysis()
    if parts is None:
        return False
    app.dependency_overrides[market_analysis_router.get_access_use_case] = (
        _access_factory(parts.logger)
    )
    app.dependency_overrides[market_analysis_router.get_market_analysis_api] = (
        get_market_analysis_api
    )
    app.include_router(market_analysis_router.router)
    if platform_factory is not None:
        try:
            _runtime = build_runtime(platform_factory(), parts.logger)
            _ticker_wanted = parts.ticker_enabled
        except Exception as e:  # noqa: BLE001 — 회차 조립 실패가 API·앱 기동을 막지 않는다
            parts.logger.warning(
                "market_analysis runtime assembly failed — rounds disabled", exception=e
            )
            _runtime = None
    return True


def start_market_analysis() -> bool:
    """lifespan 시작에서 부른다. 회차 실행기를 켠다(설정이 허락할 때만)."""
    if _runtime is None or not _ticker_wanted:
        return False
    _runtime.ticker.start()
    return True


async def close_market_analysis() -> None:
    """lifespan 종료에서 부른다. 실행 중
    회차는 취소되고 다음 기동의 recover 가 회수한다."""
    if _runtime is not None:
        await _runtime.ticker.stop()


def _access_factory(logger: LoggerInterface):
    """요청 세션 스코프 — 권한은 요청마다 DB 에서 읽는다 (회수 즉시 반영)."""

    def factory(session: AsyncSession = Depends(get_session)) -> GetAccessUseCase:
        return GetAccessUseCase(
            PermissionCodesReader(PermissionRepository(session, logger), logger), logger
        )

    return factory
