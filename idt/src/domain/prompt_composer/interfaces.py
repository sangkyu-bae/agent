"""prompt_composer 도메인 포트 — 구현은 infrastructure 가 제공한다.

Design Ref: §9.3.

포트를 3개로 나눈 이유(§7.2): `ToolMetaReaderPort` 를 분리하면 UseCase 가
tool_catalog 인프라를 직접 알지 않고, 도구 메타의 출처를 나중에 바꿔도
(카탈로그 → MCP 실시간 list_tools) UseCase 는 무변경으로 남는다.
"""
from typing import Protocol

from src.domain.prompt_composer.schemas import (
    PROMPT_SOURCE_LLM,
    ComposedPrompt,
    PromptSections,
    ToolMeta,
)


class PromptGeneratorPort(Protocol):
    """자연어 재료 → 프롬프트 섹션 생성기 (LLM 구현 예정)."""

    async def generate(
        self,
        user_request: str,
        metas: tuple[ToolMeta, ...],
        intent: dict | None,
        history: list[dict],
        request_id: str,
    ) -> tuple[PromptSections, bool, str | None, int]:
        """→ (sections, degraded, reason, elapsed_ms).

        Design §2.4 P5 — **예외를 던지지 않는다.** 모든 실패(예외·타임아웃·
        스키마 위반·빈 결과)를 흡수해 degraded=True 와 폴백 섹션으로 반환한다.
        호출부에 try/except 가 생기면 실패 경로가 2벌이 되므로 계약으로 못 박는다.
        """
        ...


class ToolMetaReaderPort(Protocol):
    """tool_id 목록 → 카탈로그 메타 조회."""

    async def fetch(
        self, tool_ids: tuple[str, ...]
    ) -> tuple[tuple[ToolMeta, ...], tuple[str, ...]]:
        """→ (찾은 메타, 못 찾은 tool_id).

        비활성(`is_active=false`) 도구는 못 찾은 것으로 취급한다 (Design E6).
        요청 순서를 보존한다 — 프롬프트 도구 블록 순서가 요청마다 흔들리면
        조립 결정성(SC-03)의 상위 계약이 깨진다.
        """
        ...


class PromptRepositoryPort(Protocol):
    """세션/버전 영속화."""

    async def create_session(
        self, user_id: str, user_request: str, agent_id: str | None
    ) -> str:
        """새 세션 생성 → session_id."""
        ...

    async def find_session(self, session_id: str, user_id: str) -> object | None:
        """소유자 일치 세션 조회. 없거나 타인 소유면 None (Design E9 → 404)."""
        ...

    async def append_version(
        self,
        session_id: str,
        prompt: ComposedPrompt,
        intent_snapshot: dict | None,
        tool_ids: tuple[str, ...],
        source: str = PROMPT_SOURCE_LLM,
    ) -> tuple[str, int]:
        """버전 추가 → (version_id, version_no).

        version_no 는 세션 내 MAX+1 이다. 동시 요청 충돌은 구현이 1회 재시도한다
        (Design E10). 커밋은 하지 않는다 — 트랜잭션 경계는 `get_session` 이다.

        agent-create-wizard Design Ref: §3.4 — `source` 는 기본값을 가지므로
        기존 호출부(compose 경로)는 무변경으로 남는다 (additive 확장 관례).
        """
        ...

    async def list_versions(self, session_id: str) -> list:
        """세션의 버전 목록을 **최신순**으로 반환한다 (Design §4.2 · FR-09).

        소유권 검사는 하지 않는다 — 호출 전에 `find_session` 으로 확인한 뒤
        부르는 것이 계약이다 (검사 지점을 한 곳에 모은다).
        """
        ...

    async def bind_agent(
        self, session_id: str, user_id: str, agent_id: str
    ) -> str | None:
        """agent_id 백필 → "ok" | "conflict" | None(미존재/타인).

        이미 바인딩된 세션은 덮어쓰지 않는다 (Design §4.3 → 409).
        """
        ...
