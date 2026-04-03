"""PromptGenerator: LLM으로 Supervisor 시스템 프롬프트 자동 생성."""
from langchain_openai import ChatOpenAI

from src.domain.agent_builder.schemas import ToolMeta, WorkflowSkeleton
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class PromptGenerator:
    """LLM Step2: 선택된 도구 + 사용자 요청 → 시스템 프롬프트 자동 생성."""

    _SYSTEM_PROMPT = """\
당신은 AI 에이전트 시스템 프롬프트 작성 전문가입니다.
아래 정보를 바탕으로 Supervisor 에이전트용 시스템 프롬프트를 작성하세요.

[형식]
1. 에이전트 목적 (1~2문장)
2. [역할] 섹션: 각 워커의 역할과 언제 사용하는지
3. [동작 원칙] 섹션: 실행 순서, 응답 언어, 주의사항

[요구사항]
- 사용자가 읽고 수정하기 쉽게 작성하세요.
- 한국어로 작성하세요.
- 2000자 이내로 작성하세요.
"""

    def __init__(self, llm: ChatOpenAI, logger: LoggerInterface) -> None:
        self._llm = llm
        self._logger = logger

    async def generate(
        self,
        user_request: str,
        skeleton: WorkflowSkeleton,
        tool_metas: list[ToolMeta],
        request_id: str,
    ) -> str:
        """시스템 프롬프트 생성."""
        self._logger.info("PromptGenerator start", request_id=request_id)
        try:
            worker_info = "\n".join(
                f"- {w.worker_id} ({meta.name}): {w.description}"
                for w, meta in zip(
                    sorted(skeleton.workers, key=lambda x: x.sort_order),
                    tool_metas,
                )
            )
            user_content = (
                f"사용자 요청: {user_request}\n\n"
                f"선택된 워커:\n{worker_info}\n\n"
                f"실행 순서 힌트: {skeleton.flow_hint}"
            )
            result = await self._llm.ainvoke([
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ])
            prompt = result.content
            self._logger.info(
                "PromptGenerator done",
                request_id=request_id,
                prompt_length=len(prompt),
            )
            return prompt
        except Exception as e:
            self._logger.error("PromptGenerator failed", exception=e, request_id=request_id)
            raise
