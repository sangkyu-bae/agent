"""retrieval-observability §6-10: 메시지 기준 검색 근거 조회 API.

GET /api/v1/conversations/messages/{message_id}/retrievals —
응답 그룹핑 / 권한(본인·admin·타인 403) / 미존재 404 / run 없음 빈 200.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_run_router import (
    get_message_retrievals_use_case,
    router,
)
from src.application.agent_run.exceptions import (
    MessageAccessDeniedError,
    MessageNotFoundError,
)
from src.application.agent_run.use_cases.get_message_retrievals_use_case import (
    GetMessageRetrievalsUseCase,
    MessageRetrievalsDto,
    MessageRunRetrievals,
    QueryRetrievalGroup,
    _group_by_query,
)
from src.domain.agent_run.entities import AgentRun, RetrievalSource
from src.domain.agent_run.value_objects import CostUsd, RunId, RunStatus, TokenUsage
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user


RUN_ID = "11111111-1111-1111-1111-111111111111"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_user(user_id: int = 1, role: UserRole = UserRole.USER) -> User:
    return User(
        email="user@test.com",
        password_hash="hashed",
        role=role,
        status=UserStatus.APPROVED,
        id=user_id,
    )


def _make_run(user_id: str = "1") -> AgentRun:
    return AgentRun(
        id=RunId(RUN_ID),
        conversation_id="conv-1",
        user_id=user_id,
        agent_id="general-chat",
        llm_model_id="m-1",
        user_message_id=42,
        status=RunStatus.SUCCESS,
        langgraph_thread_id="thread-1",
        langsmith_trace_id=None,
        langsmith_run_url="https://smith.langchain.com/r/abc",
        token_usage=TokenUsage(100, 50, 150),
        cost_usd=CostUsd(),
        llm_call_count=1,
        started_at=_now(),
        ended_at=_now(),
        latency_ms=100,
        error_message=None,
        error_stack=None,
    )


def _make_retrieval(
    rid: str, chunk_id: str, search_query: str | None, rank: int,
) -> RetrievalSource:
    return RetrievalSource(
        id=rid,
        run_id=RunId(RUN_ID),
        tool_call_id="tc-1",
        collection_name="finance-docs",
        document_id="doc-1",
        chunk_id=chunk_id,
        score=0.9,
        rank_index=rank,
        content_preview="미리보기",
        metadata_json=None,
        created_at=_now(),
        search_query=search_query,
        query_source="multi_query" if search_query else None,
        search_mode="hybrid",
        bm25_score=5.5,
        vector_score=0.88,
        fusion_source="both",
    )


def _make_dto() -> MessageRetrievalsDto:
    retrievals = [
        _make_retrieval("r1", "c1", "쿼리A", 1),
        _make_retrieval("r2", "c2", "쿼리A", 2),
        _make_retrieval("r3", "c3", "쿼리B", 3),
    ]
    return MessageRetrievalsDto(
        message_id=42,
        runs=[
            MessageRunRetrievals(
                run=_make_run(), groups=_group_by_query(retrievals),
            )
        ],
    )


def _make_app(uc, user_func) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = user_func
    app.dependency_overrides[get_message_retrievals_use_case] = lambda: uc
    return TestClient(app)


class TestMessageRetrievalsEndpoint:
    def test_returns_grouped_retrievals_for_owner(self):
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=_make_dto())
        client = _make_app(uc, lambda: _make_user(user_id=1))

        resp = client.get("/api/v1/conversations/messages/42/retrievals")

        assert resp.status_code == 200
        body = resp.json()
        assert body["message_id"] == 42
        assert len(body["runs"]) == 1
        run = body["runs"][0]
        assert run["run_id"] == RUN_ID
        assert run["agent_id"] == "general-chat"
        assert run["langsmith_run_url"] == "https://smith.langchain.com/r/abc"
        # 쿼리A(2건) / 쿼리B(1건) 그룹
        assert len(run["groups"]) == 2
        g_a = run["groups"][0]
        assert g_a["search_query"] == "쿼리A"
        assert [s["chunk_id"] for s in g_a["sources"]] == ["c1", "c2"]
        assert g_a["sources"][0]["bm25_score"] == 5.5
        assert g_a["sources"][0]["fusion_source"] == "both"

    def test_returns_404_when_message_missing(self):
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=MessageNotFoundError(99))
        client = _make_app(uc, lambda: _make_user())

        resp = client.get("/api/v1/conversations/messages/99/retrievals")

        assert resp.status_code == 404

    def test_returns_403_for_other_user(self):
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=MessageAccessDeniedError(42))
        client = _make_app(uc, lambda: _make_user(user_id=2))

        resp = client.get("/api/v1/conversations/messages/42/retrievals")

        assert resp.status_code == 403

    def test_returns_empty_runs_when_no_observability(self):
        uc = MagicMock()
        uc.execute = AsyncMock(
            return_value=MessageRetrievalsDto(message_id=42, runs=[])
        )
        client = _make_app(uc, lambda: _make_user())

        resp = client.get("/api/v1/conversations/messages/42/retrievals")

        assert resp.status_code == 200
        assert resp.json()["runs"] == []


import pytest


def _make_permission_uc(message_user_id: str, runs=None):
    """UseCase 레벨 소유 검증용 헬퍼 — 본인/타인/admin."""
    message = MagicMock()
    message.user_id.value = message_user_id

    msg_repo = MagicMock()
    msg_repo.find_by_id = AsyncMock(return_value=message)
    run_repo = MagicMock()
    run_repo.find_runs_by_user_message = AsyncMock(return_value=runs or [])
    run_repo.find_retrievals = AsyncMock(return_value=[])
    return GetMessageRetrievalsUseCase(
        agent_run_repo=run_repo,
        message_repo=msg_repo,
        logger=MagicMock(),
    )


@pytest.mark.asyncio
async def test_use_case_owner_allowed():
    uc = _make_permission_uc(message_user_id="1")
    dto = await uc.execute(message_id=42, requesting_user_id="1", is_admin=False)
    assert dto.message_id == 42
    assert dto.runs == []


@pytest.mark.asyncio
async def test_use_case_other_user_denied():
    uc = _make_permission_uc(message_user_id="1")
    with pytest.raises(MessageAccessDeniedError):
        await uc.execute(message_id=42, requesting_user_id="2", is_admin=False)


@pytest.mark.asyncio
async def test_use_case_admin_allowed():
    uc = _make_permission_uc(message_user_id="1")
    dto = await uc.execute(message_id=42, requesting_user_id="99", is_admin=True)
    assert dto.message_id == 42


@pytest.mark.asyncio
async def test_use_case_message_not_found():
    uc = _make_permission_uc(message_user_id="1")
    uc._message_repo.find_by_id = AsyncMock(return_value=None)
    with pytest.raises(MessageNotFoundError):
        await uc.execute(message_id=42, requesting_user_id="1", is_admin=False)
