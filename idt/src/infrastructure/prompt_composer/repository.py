"""prompt_composer 영속 어댑터 — 도구 메타 조회 + 세션/버전 저장.

Design Ref: §9.3.

DB-001: commit/rollback 호출 금지 — 트랜잭션 경계는 `get_session` dependency 가
소유한다. 여기서는 add/flush/execute/scalar 만 쓴다.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.prompt_composer.schemas import (
    PROMPT_SOURCE_LLM,
    ComposedPrompt,
    PromptSections,
    ToolMeta,
)
from src.infrastructure.mcp_registry.models import MCPServerModel
from src.infrastructure.prompt_composer.models import (
    PromptSessionModel,
    PromptVersionModel,
)
from src.infrastructure.tool_catalog.models import ToolCatalogModel

# prompt-depth FR-12 — 7섹션 구조. V062 가 이 용도로 넣어둔 컬럼이라 마이그레이션이
# 없다. 기존 `schema_version=1` 행은 그대로 읽힌다 (조회가 `assembled` 만 쓴다).
_SCHEMA_VERSION = 2
_BIND_OK = "ok"
_BIND_CONFLICT = "conflict"


def _now() -> datetime:
    """DB 컬럼이 naive DATETIME 이므로 UTC naive 로 맞춘다."""
    return datetime.now(UTC).replace(tzinfo=None)


class ToolCatalogMetaReader:
    """tool_id 목록 → `ToolMeta` 투영 (`ToolMetaReaderPort` 구현).

    비활성 도구는 존재하지 않는 것으로 취급한다 (Design E6).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def fetch(
        self, tool_ids: tuple[str, ...]
    ) -> tuple[tuple[ToolMeta, ...], tuple[str, ...]]:
        """→ (찾은 메타, 못 찾은 tool_id). **요청 순서를 보존한다.**

        순서 보존은 취향이 아니다 — 도구 블록 순서가 요청마다 흔들리면 같은
        입력이 다른 프롬프트를 낳아 조립 결정성(SC-03)의 상위 계약이 깨진다.
        """
        wanted = _dedupe(tool_ids)
        if not wanted:
            return (), ()
        found = await self._load(wanted)
        metas = tuple(found[tid] for tid in wanted if tid in found)
        unknown = tuple(tid for tid in wanted if tid not in found)
        return metas, unknown

    async def _load(self, wanted: tuple[str, ...]) -> dict[str, ToolMeta]:
        stmt = (
            select(ToolCatalogModel, MCPServerModel.name)
            .outerjoin(
                MCPServerModel, ToolCatalogModel.mcp_server_id == MCPServerModel.id
            )
            .where(
                ToolCatalogModel.tool_id.in_(wanted),
                ToolCatalogModel.is_active.is_(True),
            )
        )
        rows = (await self._session.execute(stmt)).all()
        return {
            tool.tool_id: ToolMeta(
                tool_id=tool.tool_id,
                name=tool.name,
                description=tool.description or "",
                source=tool.source,
                server_name=server_name,
            )
            for tool, server_name in rows
        }


class PromptRepository:
    """`prompt_session` / `prompt_version` 저장소 (`PromptRepositoryPort` 구현)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── 세션 ────────────────────────────────────────────────────────────

    async def create_session(
        self, user_id: str, user_request: str, agent_id: str | None
    ) -> str:
        now = _now()
        session_id = str(uuid.uuid4())
        self._session.add(
            PromptSessionModel(
                id=session_id,
                user_id=user_id,
                agent_id=agent_id,
                user_request=user_request,
                created_at=now,
                updated_at=now,
            )
        )
        await self._session.flush()
        return session_id

    async def find_session(
        self, session_id: str, user_id: str
    ) -> PromptSessionModel | None:
        """소유자 일치 세션만 반환한다. 타인 소유는 None → 404 (Design E9)."""
        stmt = select(PromptSessionModel).where(
            PromptSessionModel.id == session_id,
            PromptSessionModel.user_id == user_id,
        )
        return await self._session.scalar(stmt)

    # ── 버전 ────────────────────────────────────────────────────────────

    async def append_version(
        self,
        session_id: str,
        prompt: ComposedPrompt,
        intent_snapshot: dict | None,
        tool_ids: tuple[str, ...],
        source: str = PROMPT_SOURCE_LLM,
    ) -> tuple[str, int]:
        """버전 추가 → (version_id, version_no).

        Design E10 — 동시 요청이 같은 version_no 를 잡으면 `uq_session_version`
        이 거부한다. 1회만 재조회 후 재시도하고, 그래도 실패하면 전파한다.
        무한 재시도는 락 경합만 키운다.
        """
        try:
            return await self._insert_version(
                session_id, prompt, intent_snapshot, tool_ids, source
            )
        except IntegrityError:
            return await self._insert_version(
                session_id, prompt, intent_snapshot, tool_ids, source
            )

    async def _insert_version(
        self,
        session_id: str,
        prompt: ComposedPrompt,
        intent_snapshot: dict | None,
        tool_ids: tuple[str, ...],
        source: str = PROMPT_SOURCE_LLM,
    ) -> tuple[str, int]:
        version_no = await self._next_version_no(session_id)
        version_id = str(uuid.uuid4())
        self._session.add(
            PromptVersionModel(
                id=version_id,
                session_id=session_id,
                version_no=version_no,
                schema_version=_SCHEMA_VERSION,
                source=source,
                sections=_sections_to_json(prompt.sections),
                assembled=prompt.assembled,
                intent_snapshot=intent_snapshot,
                tool_ids=list(tool_ids),
                degraded=prompt.degraded,
                reason=prompt.reason,
                elapsed_ms=prompt.elapsed_ms,
                created_at=_now(),
            )
        )
        await self._session.flush()
        return version_id, version_no

    async def _next_version_no(self, session_id: str) -> int:
        stmt = select(func.max(PromptVersionModel.version_no)).where(
            PromptVersionModel.session_id == session_id
        )
        current = await self._session.scalar(stmt)
        return (current or 0) + 1

    async def list_versions(self, session_id: str) -> list[PromptVersionModel]:
        """최신 버전부터 반환한다 (Design §4.2)."""
        stmt = (
            select(PromptVersionModel)
            .where(PromptVersionModel.session_id == session_id)
            .order_by(PromptVersionModel.version_no.desc())
        )
        return list((await self._session.scalars(stmt)).all())

    # ── agent_id 백필 ───────────────────────────────────────────────────

    async def bind_agent(
        self, session_id: str, user_id: str, agent_id: str
    ) -> str | None:
        """→ "ok" | "conflict" | None(미존재/타인).

        Design §4.3 — 이미 바인딩된 세션은 덮어쓰지 않는다(409). `agent_id` 의
        실존 여부는 검증하지 않는다: agent_builder 리포지토리에 의존하면
        "기존 경로 물리적 무변경"(D1)이 깨진다.
        """
        found = await self.find_session(session_id, user_id)
        if found is None:
            return None
        if found.agent_id:
            return _BIND_CONFLICT
        stmt = (
            update(PromptSessionModel)
            .where(PromptSessionModel.id == session_id)
            .values(agent_id=agent_id, updated_at=_now())
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return _BIND_OK


# ── 직렬화 ──────────────────────────────────────────────────────────────────


def _sections_to_json(sections: PromptSections) -> dict:
    """VO → JSON (prompt-depth §3.3 — 7섹션).

    역방향 파서는 여전히 없다: 조회 API 는 `assembled` 텍스트만 쓰므로
    `schema_version` 1/2 분기가 필요 없다 (prompt-depth §1.3 R-07 실측).

    키 순서·집합은 `PromptSections` / `_PromptDraft` 와 같아야 한다 (§3.4).
    `context` 는 None 이어도 **키를 남긴다** — 집합 비교가 키로 이뤄지고,
    "없음"을 키 부재로 표현하면 유실과 구분되지 않는다.
    """
    context = sections.context
    return {
        "purpose": sections.purpose,
        "identity": sections.identity,
        "context": (
            {
                "constraints": list(context.constraints),
                "background": list(context.background),
            }
            if context is not None
            else None
        ),
        "roles": [
            {"title": r.title, "detail": r.detail} for r in sections.roles
        ],
        "tool_guides": [
            {
                "tool_id": g.tool_id,
                "name": g.name,
                "when": g.when,
                "how": g.how,
                "caution": g.caution,
            }
            for g in sections.tool_guides
        ],
        "workflows": [
            {"situation": w.situation, "steps": list(w.steps)}
            for w in sections.workflows
        ],
        "style": sections.style,
        "principles": list(sections.principles),
    }


def _dedupe(tool_ids: tuple[str, ...]) -> tuple[str, ...]:
    """순서를 보존하며 중복을 제거한다."""
    seen: set[str] = set()
    result: list[str] = []
    for tid in tool_ids:
        if tid in seen:
            continue
        seen.add(tid)
        result.append(tid)
    return tuple(result)
