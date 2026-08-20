"""시스템 프롬프트 생성 UseCase — 흐름 제어.

Design Ref: §2.1 / §2.2.

흐름 6단계:
  ① tool_ids → 카탈로그 메타 조회      (ToolMetaReaderPort)
  ② 프롬프트 섹션 생성                 (PromptGeneratorPort — 예외 안 던짐)
  ③ 환각 도구 폐기                     (Policy)
  ④ 결정적 조립                        (Policy)
  ⑤ 세션 확보 (신규 생성 또는 소유권 확인)
  ⑥ 버전 append

**try/except 가 없다** (Design §2.4 P5): LLM 실패는 어댑터가 전부 흡수해
degraded 로 돌려주므로 여기서 잡을 것이 없고, DB 실패는 잡으면 안 된다 —
저장이 실패하면 version_id 를 줄 수 없으므로 200 으로 위장하면 호출자가 없는
버전을 참조하게 된다 (Design §6.2).
"""
from dataclasses import dataclass

from src.application.prompt_composer.errors import (
    AgentAlreadyBoundError,
    PromptSessionNotFoundError,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.prompt_composer.interfaces import (
    PromptGeneratorPort,
    PromptRepositoryPort,
    ToolMetaReaderPort,
)
from src.domain.prompt_composer.policies import PromptAssemblyPolicy
from src.domain.prompt_composer.schemas import ComposedPrompt

_BIND_CONFLICT = "conflict"


@dataclass(frozen=True)
class ComposeResult:
    """생성 결과 + 영속 식별자."""

    session_id: str
    version_id: str
    version_no: int
    prompt: ComposedPrompt


class ComposePromptUseCase:
    """프롬프트 생성·조회·바인딩. 이 모듈의 애플리케이션 서비스."""

    def __init__(
        self,
        generator: PromptGeneratorPort,
        tool_reader: ToolMetaReaderPort,
        repository: PromptRepositoryPort,
        logger: LoggerInterface,
    ) -> None:
        self._generator = generator
        self._tool_reader = tool_reader
        self._repository = repository
        self._logger = logger

    async def compose(
        self,
        user_id: str,
        user_request: str,
        request_id: str,
        history: list | None = None,
        intent: dict | None = None,
        tool_ids: tuple[str, ...] = (),
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> ComposeResult:
        """자연어 요청 → 구조화 프롬프트 + 저장된 버전.

        Raises:
            PromptSessionNotFoundError: session_id 가 없거나 타인 소유 (→ 404)
        """
        metas, unknown = await self._tool_reader.fetch(tool_ids)
        usable_intent = _usable_intent(intent)
        sections, degraded, reason, elapsed = await self._generator.generate(
            user_request,
            metas,
            usable_intent,
            PromptAssemblyPolicy.clamp_history(history),
            request_id,
        )
        prompt = self._finalize(sections, metas, degraded, reason, unknown, elapsed)
        resolved_id = await self._resolve_session(
            user_id, user_request, session_id, agent_id
        )
        version_id, version_no = await self._repository.append_version(
            resolved_id,
            prompt,
            usable_intent,
            tuple(g.tool_id for g in prompt.sections.tool_guides),
        )
        self._log_done(request_id, resolved_id, version_no, prompt)
        return ComposeResult(resolved_id, version_id, version_no, prompt)

    async def get_session(self, session_id: str, user_id: str):
        """→ (session, versions). 없거나 타인 소유면 예외 (→ 404)."""
        found = await self._repository.find_session(session_id, user_id)
        if found is None:
            raise PromptSessionNotFoundError(session_id)
        return found, await self._repository.list_versions(session_id)

    async def bind_agent(self, session_id: str, user_id: str, agent_id: str) -> None:
        """agent_id 백필. 이미 바인딩됐으면 덮어쓰지 않는다 (→ 409)."""
        outcome = await self._repository.bind_agent(session_id, user_id, agent_id)
        if outcome is None:
            raise PromptSessionNotFoundError(session_id)
        if outcome == _BIND_CONFLICT:
            raise AgentAlreadyBoundError(session_id)

    # ── 내부 ────────────────────────────────────────────────────────────

    def _finalize(
        self, sections, metas, degraded, reason, unknown, elapsed
    ) -> ComposedPrompt:
        """폐기 → 조립. 규칙은 Policy 가 갖고 여기서는 순서만 정한다."""
        known = {meta.tool_id: meta for meta in metas}
        cleaned, dropped = PromptAssemblyPolicy.drop_hallucinated(sections, known)
        return ComposedPrompt(
            sections=cleaned,
            assembled=PromptAssemblyPolicy.assemble(cleaned),
            degraded=degraded,
            reason=reason,
            dropped_tool_ids=dropped,
            unknown_tool_ids=unknown,
            elapsed_ms=elapsed,
        )

    async def _resolve_session(
        self,
        user_id: str,
        user_request: str,
        session_id: str | None,
        agent_id: str | None,
    ) -> str:
        """기존 세션이면 소유권 확인, 아니면 신규 생성 (FR-08)."""
        if session_id is None:
            return await self._repository.create_session(
                user_id, user_request, agent_id
            )
        found = await self._repository.find_session(session_id, user_id)
        if found is None:
            raise PromptSessionNotFoundError(session_id)
        return session_id

    def _log_done(
        self, request_id: str, session_id: str, version_no: int, prompt
    ) -> None:
        """프롬프트 본문·요청 원문은 남기지 않는다 (PII 위험). 개수만 남긴다."""
        self._logger.info(
            "prompt version stored",
            request_id=request_id,
            session_id=session_id,
            version_no=version_no,
            degraded=prompt.degraded,
            reason=prompt.reason,
            guide_count=len(prompt.sections.tool_guides),
            dropped_count=len(prompt.dropped_tool_ids),
            unknown_count=len(prompt.unknown_tool_ids),
            latency_ms=prompt.elapsed_ms,
        )


def _usable_intent(intent: dict | None) -> dict | None:
    """FR-13 — 판정 실패(degraded)는 '의도 없음'과 동일하게 취급한다.

    프롬프트 부착에서 빠질 뿐 아니라 `intent_snapshot` 에도 저장하지 않는다.
    오염된 판정을 근거로 남기면 나중에 이 버전을 해석할 때 오도한다.
    """
    if not intent or intent.get("degraded"):
        return None
    return intent
