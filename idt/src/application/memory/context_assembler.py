"""MemoryContextAssembler — General Chat 주입 블록 조립 (agent-memory Design §3-3).

앱 싱글톤(GeneralChatUseCase)에서 요청별 세션이 필요한 문제를
RunScopedWikiSearch/RunTracker와 동일한 session_factory per-call 패턴으로 해결:
호출마다 짧은 세션을 열어 조회하고 즉시 닫는다.

- FR-05: 캡 절단 시 debug 로그
- FR-06: 0건이면 빈 문자열 (빈 헤더 금지)
- FR-07: 어떤 실패도 채팅 장애로 전파하지 않음 — warning 후 "" 반환
- FR-09: 블록에 보수적 사용 지침 고정 (금융 도메인 오염 방지)
"""
from typing import Callable

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.memory.entity import Memory, MemoryType
from src.domain.memory.policies import MemoryPolicy

_TYPE_LABELS = {
    MemoryType.PROFILE: "프로필",
    MemoryType.DOMAIN_TERM: "용어",
    MemoryType.PREFERENCE: "선호",
    MemoryType.EPISODE: "참고",
}

_BLOCK_HEADER = (
    "[사용자 메모리]\n"
    "다음은 사용자가 직접 등록한 배경 정보입니다. 답변에 자연스럽게 반영하되,\n"
    "내용이 현재 질문과 모순되거나 불확실하면 사용자에게 확인하세요.\n"
)


class MemoryContextAssembler:
    def __init__(
        self,
        session_factory,
        logger: LoggerInterface,
        token_cap: int,
        repo_builder: Callable | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger
        self._token_cap = token_cap
        self._repo_builder = repo_builder or self._default_repo_builder

    async def build_block(self, user_id: str, request_id: str) -> str:
        try:
            async with self._session_factory() as session:
                repo = self._repo_builder(session)
                memories = await repo.find_active_by_user(user_id, request_id)
            if not memories:
                return ""  # FR-06

            ordered = MemoryPolicy.sort_for_injection(memories)
            included, truncated = MemoryPolicy.truncate_to_budget(
                ordered, self._token_cap
            )
            if truncated:
                self._logger.debug(
                    "memory block truncated",
                    request_id=request_id,
                    total=len(ordered),
                    included=len(included),
                    token_cap=self._token_cap,
                )
            self._logger.info(
                "memory block injected", request_id=request_id, count=len(included),
            )
            return self._render(included)
        except Exception as e:
            self._logger.warning(
                "memory load failed — inject skipped",
                request_id=request_id,
                exception=e,
            )  # FR-07
            return ""

    def _default_repo_builder(self, session):
        from src.infrastructure.memory.repository import MemoryRepository

        return MemoryRepository(session, self._logger)

    @staticmethod
    def _render(memories: list[Memory]) -> str:
        lines = "\n".join(
            f"- ({_TYPE_LABELS[m.mem_type]}) {m.content}" for m in memories
        )
        return f"{_BLOCK_HEADER}{lines}\n---\n\n"
