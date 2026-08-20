"""prompt-composer Design §8.4 — 영속 계층 테스트.

인메모리 SQLite 로 실제 SQLAlchemy 세션을 돌린다. 커밋 금지 규칙(DB-001)을
지키는지, version_no 가 세션 내에서 단조 증가하는지, 소유권 격리가 되는지가
핵심이다.

SQLite 는 MySQL 의 ON DELETE CASCADE 를 기본 비활성으로 두므로 PRAGMA 로 켠다.
"""
from dataclasses import replace
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from src.domain.prompt_composer.schemas import (
    PROMPT_SOURCE_HUMAN,
    PROMPT_SOURCE_LLM,
    ComposedPrompt,
    ContextSection,
    PromptSections,
    RoleSection,
    ToolGuide,
    WorkflowSection,
)
from src.infrastructure.mcp_registry.models import MCPServerModel
from src.infrastructure.persistence.models.base import Base
from src.infrastructure.prompt_composer.models import (
    PromptSessionModel,
    PromptVersionModel,
)
from src.infrastructure.prompt_composer.repository import (
    PromptRepository,
    ToolCatalogMetaReader,
)
from src.infrastructure.tool_catalog.models import ToolCatalogModel

_USER = "user-1"
_OTHER = "user-2"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                PromptSessionModel.__table__,
                PromptVersionModel.__table__,
                ToolCatalogModel.__table__,
                MCPServerModel.__table__,
            ],
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed_tools(session):
    session.add(
        MCPServerModel(
            id="srv-1",
            user_id=_USER,
            name="사내 문서 서버",
            **_mcp_server_extras(),
        )
    )
    session.add_all(
        [
            ToolCatalogModel(
                id="c1",
                tool_id="internal:excel_export",
                source="internal",
                name="엑셀 내보내기",
                description="표를 엑셀로 내보낸다",
                is_active=True,
                is_builtin=False,
                created_at=_now(),
                updated_at=_now(),
            ),
            ToolCatalogModel(
                id="c2",
                tool_id="mcp:srv-1:search_docs",
                source="mcp",
                mcp_server_id="srv-1",
                name="문서 검색",
                description="사내 문서를 찾는다",
                is_active=True,
                is_builtin=False,
                created_at=_now(),
                updated_at=_now(),
            ),
            ToolCatalogModel(
                id="c3",
                tool_id="internal:disabled_tool",
                source="internal",
                name="비활성 도구",
                description="꺼져 있다",
                is_active=False,
                is_builtin=False,
                created_at=_now(),
                updated_at=_now(),
            ),
        ]
    )
    await session.flush()


def _mcp_server_extras() -> dict:
    """MCPServerModel 의 NOT NULL 부가 컬럼을 런타임에 채운다.

    모델 정의가 바뀌어도 이 테스트가 먼저 깨지지 않도록 기본값 없는 컬럼만 훑는다.
    """
    extras: dict = {}
    for column in MCPServerModel.__table__.columns:
        if column.name in ("id", "user_id", "name"):
            continue
        if column.nullable or column.default is not None or column.server_default:
            continue
        extras[column.name] = _placeholder_for(column)
    return extras


def _placeholder_for(column):
    type_name = column.type.__class__.__name__.lower()
    if "int" in type_name:
        return 0
    if "bool" in type_name:
        return False
    if "date" in type_name or "time" in type_name:
        return _now()
    if "json" in type_name:
        return {}
    return "x"


def _base_sections() -> PromptSections:
    return PromptSections(
        purpose="목적",
        roles=(RoleSection(title="검색", detail="찾는다"),),
        tool_guides=(
            ToolGuide(tool_id="t1", name="도구", when="언제", how="어떻게"),
        ),
        principles=("한국어로 답한다",),
    )


def _full_sections() -> PromptSections:
    """prompt-depth — 신규 3필드까지 채운 섹션."""
    return replace(
        _base_sections(),
        identity="규정 전문가입니다.",
        context=ContextSection(
            constraints=("추측하지 않는다",), background=("2026 개정판 기준",)
        ),
        workflows=(
            WorkflowSection(situation="일반 요청", steps=("찾는다", "답한다")),
        ),
        style="격식체로 답한다.",
    )


def _prompt(
    assembled: str = "조립된 프롬프트",
    degraded: bool = False,
    sections: PromptSections | None = None,
) -> ComposedPrompt:
    return ComposedPrompt(
        sections=sections or _base_sections(),
        assembled=assembled,
        degraded=degraded,
        reason="timeout" if degraded else None,
        elapsed_ms=1234,
    )


# ── ToolCatalogMetaReader (Design E6) ───────────────────────────────────────


async def test_fetch_returns_metas_for_known_ids(session):
    await _seed_tools(session)
    reader = ToolCatalogMetaReader(session)
    metas, unknown = await reader.fetch(("internal:excel_export",))
    assert unknown == ()
    assert metas[0].name == "엑셀 내보내기"
    assert metas[0].source == "internal"


async def test_fetch_reports_missing_ids_as_unknown(session):
    await _seed_tools(session)
    reader = ToolCatalogMetaReader(session)
    metas, unknown = await reader.fetch(("internal:excel_export", "ghost:tool"))
    assert tuple(m.tool_id for m in metas) == ("internal:excel_export",)
    assert unknown == ("ghost:tool",)


async def test_fetch_treats_inactive_tool_as_unknown(session):
    await _seed_tools(session)
    reader = ToolCatalogMetaReader(session)
    metas, unknown = await reader.fetch(("internal:disabled_tool",))
    assert metas == ()
    assert unknown == ("internal:disabled_tool",)


async def test_fetch_preserves_request_order(session):
    """도구 순서가 요청마다 흔들리면 조립 결정성(SC-03)의 상위 계약이 깨진다."""
    await _seed_tools(session)
    reader = ToolCatalogMetaReader(session)
    ids = ("mcp:srv-1:search_docs", "internal:excel_export")
    metas, _ = await reader.fetch(ids)
    assert tuple(m.tool_id for m in metas) == ids


async def test_fetch_fills_server_name_for_mcp_tools(session):
    await _seed_tools(session)
    reader = ToolCatalogMetaReader(session)
    metas, _ = await reader.fetch(("mcp:srv-1:search_docs",))
    assert metas[0].server_name == "사내 문서 서버"
    assert metas[0].source == "mcp"


async def test_fetch_with_empty_ids_makes_no_query(session):
    reader = ToolCatalogMetaReader(session)
    assert await reader.fetch(()) == ((), ())


async def test_fetch_deduplicates_repeated_ids(session):
    await _seed_tools(session)
    reader = ToolCatalogMetaReader(session)
    metas, _ = await reader.fetch(("internal:excel_export", "internal:excel_export"))
    assert len(metas) == 1


# ── PromptRepository: 세션 생성/조회 (Design SC-07) ──────────────────────────


async def test_create_session_returns_id_and_persists(session):
    repo = PromptRepository(session)
    session_id = await repo.create_session(_USER, "요청 문장", None)
    found = await session.scalar(
        select(PromptSessionModel).where(PromptSessionModel.id == session_id)
    )
    assert found is not None
    assert found.user_request == "요청 문장"
    assert found.agent_id is None


async def test_create_session_accepts_agent_id(session):
    repo = PromptRepository(session)
    session_id = await repo.create_session(_USER, "요청", "agent-9")
    found = await repo.find_session(session_id, _USER)
    assert found.agent_id == "agent-9"


async def test_find_session_returns_none_for_other_user(session):
    repo = PromptRepository(session)
    session_id = await repo.create_session(_USER, "요청", None)
    assert await repo.find_session(session_id, _OTHER) is None


async def test_find_session_returns_none_for_missing_id(session):
    repo = PromptRepository(session)
    assert await repo.find_session("does-not-exist", _USER) is None


# ── PromptRepository: 버전 append (Plan SC-08) ──────────────────────────────


async def test_append_version_starts_at_one(session):
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    _, version_no = await repo.append_version(sid, _prompt(), None, ("t1",))
    assert version_no == 1


async def test_append_version_increments_within_session(session):
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    numbers = [
        (await repo.append_version(sid, _prompt(), None, ("t1",)))[1]
        for _ in range(3)
    ]
    assert numbers == [1, 2, 3]


async def test_append_version_numbering_is_per_session(session):
    repo = PromptRepository(session)
    a = await repo.create_session(_USER, "A", None)
    b = await repo.create_session(_USER, "B", None)
    await repo.append_version(a, _prompt(), None, ())
    _, version_no = await repo.append_version(b, _prompt(), None, ())
    assert version_no == 1


async def test_append_version_persists_sections_as_json(session):
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    version_id, _ = await repo.append_version(sid, _prompt(), None, ("t1",))
    row = await session.scalar(
        select(PromptVersionModel).where(PromptVersionModel.id == version_id)
    )
    assert row.sections["purpose"] == "목적"
    assert row.sections["tool_guides"][0]["tool_id"] == "t1"
    assert row.tool_ids == ["t1"]
    # prompt-depth FR-12 — 7섹션 구조는 schema_version 2 다.
    assert row.schema_version == 2


async def test_append_version_persists_new_sections(session):
    """prompt-depth §3.3 — 신규 섹션이 직렬화에서 빠지면 조용히 유실된다."""
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    version_id, _ = await repo.append_version(
        sid, _prompt(sections=_full_sections()), None, ("t1",)
    )
    row = await session.scalar(
        select(PromptVersionModel).where(PromptVersionModel.id == version_id)
    )
    assert row.sections["identity"] == "규정 전문가입니다."
    assert row.sections["context"]["constraints"] == ["추측하지 않는다"]
    assert row.sections["context"]["background"] == ["2026 개정판 기준"]
    assert row.sections["workflows"][0]["situation"] == "일반 요청"
    assert row.sections["workflows"][0]["steps"] == ["찾는다", "답한다"]
    assert row.sections["style"] == "격식체로 답한다."


async def test_append_version_serializes_absent_context_as_null(session):
    """`context` 키 자체는 항상 존재한다 — 필드 집합 비교가 키로 이뤄지므로."""
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    version_id, _ = await repo.append_version(sid, _prompt(), None, ("t1",))
    row = await session.scalar(
        select(PromptVersionModel).where(PromptVersionModel.id == version_id)
    )
    assert "context" in row.sections
    assert row.sections["context"] is None


async def test_append_version_records_degraded_fields(session):
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    version_id, _ = await repo.append_version(sid, _prompt(degraded=True), None, ())
    row = await session.scalar(
        select(PromptVersionModel).where(PromptVersionModel.id == version_id)
    )
    assert row.degraded is True
    assert row.reason == "timeout"
    assert row.elapsed_ms == 1234


async def test_append_version_stores_intent_snapshot_verbatim(session):
    """의도 모듈 스키마가 바뀌어도 파싱하지 않고 통과 저장한다 (Design §3.4)."""
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    snapshot = {"label": "qa", "future_field": [1, 2, 3]}
    version_id, _ = await repo.append_version(sid, _prompt(), snapshot, ())
    row = await session.scalar(
        select(PromptVersionModel).where(PromptVersionModel.id == version_id)
    )
    assert row.intent_snapshot == snapshot


async def test_append_version_stores_null_snapshot_when_absent(session):
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    version_id, _ = await repo.append_version(sid, _prompt(), None, ())
    row = await session.scalar(
        select(PromptVersionModel).where(PromptVersionModel.id == version_id)
    )
    assert row.intent_snapshot is None


async def test_append_version_defaults_source_to_llm(session):
    """기존 compose 경로는 source 를 넘기지 않는다 — 회귀 잠금 (V063 additive)."""
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    version_id, _ = await repo.append_version(sid, _prompt(), None, ())
    row = await session.scalar(
        select(PromptVersionModel).where(PromptVersionModel.id == version_id)
    )
    assert row.source == PROMPT_SOURCE_LLM


async def test_append_version_persists_human_source(session):
    """agent-create-wizard §3.4 — 사람 편집본은 human 으로 구분 저장된다."""
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    version_id, _ = await repo.append_version(
        sid, _prompt(), None, (), PROMPT_SOURCE_HUMAN
    )
    row = await session.scalar(
        select(PromptVersionModel).where(PromptVersionModel.id == version_id)
    )
    assert row.source == PROMPT_SOURCE_HUMAN


async def test_mixed_sources_share_one_version_sequence(session):
    """LLM 생성본과 사람 편집본이 같은 세션의 연속 번호를 쓴다."""
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    _, first = await repo.append_version(sid, _prompt("생성본"), None, ())
    _, second = await repo.append_version(
        sid, _prompt("편집본"), None, (), PROMPT_SOURCE_HUMAN
    )
    assert (first, second) == (1, 2)


async def test_list_versions_returns_newest_first(session):
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    await repo.append_version(sid, _prompt("첫번째"), None, ())
    await repo.append_version(sid, _prompt("두번째"), None, ())
    versions = await repo.list_versions(sid)
    assert [v.version_no for v in versions] == [2, 1]


# ── PromptRepository: agent_id 백필 (Design §4.3) ───────────────────────────


async def test_bind_agent_sets_agent_id(session):
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    assert await repo.bind_agent(sid, _USER, "agent-1") == "ok"
    assert (await repo.find_session(sid, _USER)).agent_id == "agent-1"


async def test_bind_agent_conflicts_when_already_bound(session):
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", "agent-1")
    assert await repo.bind_agent(sid, _USER, "agent-2") == "conflict"
    assert (await repo.find_session(sid, _USER)).agent_id == "agent-1"


async def test_bind_agent_returns_none_for_other_user(session):
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    assert await repo.bind_agent(sid, _OTHER, "agent-1") is None


async def test_bind_agent_returns_none_for_missing_session(session):
    repo = PromptRepository(session)
    assert await repo.bind_agent("nope", _USER, "agent-1") is None


# ── DB-001: Repository 는 커밋하지 않는다 ────────────────────────────────────


async def test_repository_never_commits(session, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        type(session), "commit", lambda self: calls.append("commit")
    )
    monkeypatch.setattr(
        type(session), "rollback", lambda self: calls.append("rollback")
    )
    repo = PromptRepository(session)
    sid = await repo.create_session(_USER, "요청", None)
    await repo.append_version(sid, _prompt(), None, ())
    await repo.bind_agent(sid, _USER, "agent-1")
    assert calls == []


@pytest.mark.parametrize("method", ["commit", "rollback"])
def test_repository_source_has_no_transaction_calls(method):
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[3]
        / "src" / "infrastructure" / "prompt_composer" / "repository.py"
    ).read_text(encoding="utf-8")
    assert f".{method}()" not in source
