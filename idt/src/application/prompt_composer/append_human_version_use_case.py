"""사람이 편집한 시스템 프롬프트를 버전으로 append 하는 UseCase.

agent-create-wizard Design Ref: §3.4 / §4.5.

위저드 4단계에서 사용자가 생성된 프롬프트를 직접 고치면 그 편집본을 새 버전으로
쌓는다. LLM 재생성이 아니므로 `ComposePromptUseCase` 를 타지 않는다 —
생성기·도구 메타 조회가 전부 불필요하고, 그것들을 끌어들이면 "사람이 쓴 글을
저장한다"는 단순한 일이 LLM 경로의 실패 모드를 물려받는다.

**try/except 가 없다** (기존 모듈 관례 P5와 동일): 저장 실패는 잡으면 안 된다.
200 으로 위장하면 호출자가 없는 version_id 를 참조한다 (Design §6.2).
"""
from dataclasses import dataclass

from src.application.prompt_composer.errors import PromptSessionNotFoundError
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.prompt_composer.interfaces import PromptRepositoryPort
from src.domain.prompt_composer.schemas import (
    PROMPT_SOURCE_HUMAN,
    ComposedPrompt,
    PromptSections,
)

_EMPTY_SECTIONS = PromptSections(purpose="")
"""사람 편집본은 섹션 분해가 없다 — LLM 이 만든 구조가 아니기 때문이다."""


@dataclass(frozen=True)
class HumanVersionResult:
    """append 결과 + 영속 식별자."""

    session_id: str
    version_id: str
    version_no: int
    source: str = PROMPT_SOURCE_HUMAN


class AppendHumanVersionUseCase:
    """세션 소유권 확인 → 편집본을 human 버전으로 append."""

    def __init__(
        self, repository: PromptRepositoryPort, logger: LoggerInterface
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def append(
        self,
        session_id: str,
        user_id: str,
        assembled: str,
        tool_ids: tuple[str, ...] = (),
    ) -> HumanVersionResult:
        """편집본 저장 → (session_id, version_id, version_no, source).

        Raises:
            PromptSessionNotFoundError: 세션이 없거나 타인 소유 (→ 404)
        """
        # 소유권 검사가 append 보다 먼저다 — 검사 지점을 한 곳에 모으는
        # 기존 계약(PromptRepositoryPort.list_versions 독스트링)과 동일하다.
        found = await self._repository.find_session(session_id, user_id)
        if found is None:
            raise PromptSessionNotFoundError(session_id)
        version_id, version_no = await self._repository.append_version(
            session_id,
            self._to_prompt(assembled),
            # 편집본의 근거는 사람이다. 이전 버전의 의도를 복사해 오면
            # "이 프롬프트는 이 의도에서 나왔다"는 거짓 근거가 남는다.
            None,
            tuple(tool_ids),
            PROMPT_SOURCE_HUMAN,
        )
        self._log_done(session_id, version_no, len(assembled), len(tool_ids))
        return HumanVersionResult(session_id, version_id, version_no)

    # ── 내부 ────────────────────────────────────────────────────────────

    @staticmethod
    def _to_prompt(assembled: str) -> ComposedPrompt:
        """편집 문자열 → 저장용 VO. 관측 필드는 전부 '해당 없음' 값이다."""
        return ComposedPrompt(sections=_EMPTY_SECTIONS, assembled=assembled)

    def _log_done(
        self, session_id: str, version_no: int, length: int, tool_count: int
    ) -> None:
        """프롬프트 본문은 남기지 않는다 (PII 위험). 길이·개수만 남긴다."""
        self._logger.info(
            "human prompt version stored",
            session_id=session_id,
            version_no=version_no,
            source=PROMPT_SOURCE_HUMAN,
            prompt_length=length,
            tool_count=tool_count,
        )
