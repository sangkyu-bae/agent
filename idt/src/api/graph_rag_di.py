"""graph-rag-foundation 모듈 조립 — 코어에 끼워 넣는 단일 지점.

Design Ref: graph-rag-foundation §2.1 / D11 / Plan SC-9 — main.py 는 wire 1줄과
lifespan start/close 2줄만 둔다. wire 를 지우면 코어 훅은 비어 있고(no-op)
start/close 도 아무 일도 하지 않는다. graph_rag 패키지 import 는 여기서만 한다.

module-2 범위: 노출 판단(GraphExposure) 등록, 설정·단계·상태 API, Neo4j 드라이버.
module-3~5 에서 post_ingest·deletion·supplemental 슬롯을 이 함수에서 등록한다.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.graph_rag.admin.health_use_case import GraphHealthUseCase
from src.application.graph_rag.admin.settings_use_case import GraphRagSettingsUseCase
from src.application.graph_rag.admin.stage_use_case import ChangeStageUseCase
from src.application.graph_rag.hooks import GraphExposure
from src.domain.extension_hooks import ExtensionHooks
from src.domain.graph_rag.exceptions import GraphEmbeddingDimMismatchError
from src.domain.graph_rag.interfaces import GraphSettingsReaderPort, GraphStorePort
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.graph_rag.eval_evidence import UnverifiedEvalEvidence
from src.infrastructure.graph_rag.neo4j.store import Neo4jGraphStore, build_driver
from src.infrastructure.graph_rag.repositories import (
    GraphRagSettingRepository,
    GraphRagStageChangeRepository,
)
from src.infrastructure.graph_rag.settings_reader import CachedGraphSettingsReader

_OWNER = "graph_rag"
_BACKEND_OFF = "off"
_BACKEND_NEO4J = "neo4j"


@dataclass
class GraphRagRuntime:
    backend: str
    store: GraphStorePort | None
    reader: GraphSettingsReaderPort
    logger: LoggerInterface
    embedding_dimensions: int
    disabled_reason: str | None = None


_runtime: GraphRagRuntime | None = None


def _session_scope(session_factory: Callable[[], Any]):
    @asynccontextmanager
    async def _scope():
        async with session_factory() as session:
            async with session.begin():
                yield session

    return _scope


def _build_store(settings: Any, logger: LoggerInterface) -> GraphStorePort | None:
    backend = (settings.graph_backend or "").strip().casefold()
    if backend == _BACKEND_OFF:
        return None
    if backend != _BACKEND_NEO4J:
        logger.warning("unknown GRAPH_BACKEND — graph store disabled", value=backend)
        return None
    if not settings.neo4j_uri or not settings.neo4j_password:
        logger.warning("GRAPH_BACKEND=neo4j but NEO4J_URI/PASSWORD missing — disabled")
        return None
    try:
        driver = build_driver(
            settings.neo4j_uri,
            settings.neo4j_user,
            settings.neo4j_password,
            max_pool_size=settings.neo4j_max_pool_size,
            connect_timeout_s=settings.neo4j_connect_timeout_s,
        )
    except Exception as e:  # noqa: BLE001 — 드라이버 미설치(extra graph)·주소 오류
        logger.warning("neo4j driver build failed — graph store disabled", exception=e)
        return None
    return Neo4jGraphStore(driver, settings.neo4j_database, logger)


def wire_graph_rag(
    app: FastAPI,
    *,
    get_session: Callable[..., AsyncSession],
    session_factory: Callable[[], Any],
    hooks: ExtensionHooks,
    logger: LoggerInterface,
    settings: Any,
) -> GraphRagRuntime:
    """create_app() 에서 1회 호출. 실패해도 앱 기동을 막지 않는 값만 만든다."""
    global _runtime
    from src.api.routes import admin_graph_rag_router as admin_routes
    from src.api.routes import graph_rag_router as public_routes

    reader = CachedGraphSettingsReader(
        session_scope=_session_scope(session_factory),
        repo_factory=lambda session: GraphRagSettingRepository(session, logger),
        logger=logger,
    )
    store = _build_store(settings, logger)
    backend = _BACKEND_NEO4J if store is not None else _BACKEND_OFF
    # owner 지정 — create_app() 재호출(테스트·리로드) 시 교체, 다른 확장과는 충돌
    hooks.register(owner=_OWNER, exposure=GraphExposure(reader))

    def _settings_uc(session: AsyncSession = Depends(get_session)):
        return GraphRagSettingsUseCase(
            GraphRagSettingRepository(session, logger), reader, logger
        )

    def _stage_uc(session: AsyncSession = Depends(get_session)):
        return ChangeStageUseCase(
            GraphRagSettingRepository(session, logger),
            GraphRagStageChangeRepository(session, logger),
            UnverifiedEvalEvidence(logger),
            reader,
            logger,
        )

    def _health_uc():
        return GraphHealthUseCase(
            store=_runtime.store if _runtime else None,
            backend=_runtime.backend if _runtime else _BACKEND_OFF,
            uri=settings.neo4j_uri,
            node_limit=settings.graph_aura_free_node_limit,
            rel_limit=settings.graph_aura_free_rel_limit,
        )

    overrides = app.dependency_overrides
    overrides[admin_routes.get_graph_rag_settings_use_case] = _settings_uc
    overrides[admin_routes.get_change_stage_use_case] = _stage_uc
    overrides[admin_routes.get_graph_health_use_case] = _health_uc
    overrides[public_routes.get_graph_settings_reader] = lambda: reader
    app.include_router(admin_routes.router)
    app.include_router(public_routes.router)

    _runtime = GraphRagRuntime(
        backend=backend,
        store=store,
        reader=reader,
        logger=logger,
        embedding_dimensions=settings.graph_entity_embedding_dimensions,
    )
    logger.info("graph rag module wired", backend=backend)
    return _runtime


async def start_graph_rag() -> None:
    """lifespan startup — 스키마 멱등 생성.

    차원 불일치는 모듈 비활성, 연결 실패는 경고만.
    """
    runtime = _runtime
    if runtime is None or runtime.store is None:
        return
    try:
        await runtime.store.ensure_schema(runtime.embedding_dimensions)
    except GraphEmbeddingDimMismatchError as e:
        runtime.logger.error(
            "graph store disabled — embedding dim mismatch", exception=e
        )
        runtime.disabled_reason = str(e)
        await _close_quietly(runtime)
        runtime.store = None
    except Exception as e:  # noqa: BLE001 — Aura 정지 등은 일시적: 요청 시 재시도
        runtime.logger.warning(
            "graph schema bootstrap skipped — backend unavailable", exception=e
        )


async def close_graph_rag() -> None:
    """lifespan shutdown — best-effort."""
    runtime = _runtime
    if runtime is None or runtime.store is None:
        return
    await _close_quietly(runtime)


async def _close_quietly(runtime: GraphRagRuntime) -> None:
    try:
        await runtime.store.aclose()  # type: ignore[union-attr]
    except Exception as e:  # noqa: BLE001
        runtime.logger.warning("graph store close failed", exception=e)
