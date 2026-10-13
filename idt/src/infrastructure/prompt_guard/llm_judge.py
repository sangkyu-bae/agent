"""LlmInjectionJudge — Design Ref: §4.2 (FR-04/05), D4.

관리자 기본 모델(UtilityLLMProviderPort → is_default)로 REVIEW 구간 입력을
strict structured output 으로 판정한다. 공급자가 모델을 해석하지 못하면
JudgeUnavailableError 를 올리고 서비스가 fail-open 한다.
"""
from __future__ import annotations

import time
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.prompt_guard.exceptions import JudgeUnavailableError
from src.domain.prompt_guard.schemas import JudgeVerdict
from src.infrastructure.prompt_guard.prompts import (
    JUDGE_HUMAN_TEMPLATE,
    JUDGE_SYSTEM_PROMPT,
)


class InjectionJudgeOutput(BaseModel):
    """strict structured output — 두 필드만. 계산 필드는 코드가 채운다 (신뢰 경계)."""

    verdict: Literal["injection", "benign"] = Field(
        ...,
        description="injection = 지침 덮어쓰기·역할 탈취·프롬프트 유출·제한 해제 요구",
    )
    reason: str = Field(..., description="판정 이유 한 문장")


class LlmInjectionJudge:
    """InjectionJudgePort 구현."""

    def __init__(
        self,
        llm_provider: UtilityLLMProviderPort,
        logger: LoggerInterface,
        *,
        temperature: float = 0.0,
    ) -> None:
        self._provider = llm_provider
        self._logger = logger
        self._temperature = temperature
        self._prompt = ChatPromptTemplate.from_messages(
            [("system", JUDGE_SYSTEM_PROMPT), ("human", JUDGE_HUMAN_TEMPLATE)]
        )
        self._cached_llm: object | None = None
        self._cached_chain = None

    async def judge(self, text: str, *, request_id: str) -> JudgeVerdict:
        chain = await self._resolve_chain()
        started = time.monotonic()
        out: InjectionJudgeOutput = await chain.ainvoke({"user_input": text})
        latency_ms = int((time.monotonic() - started) * 1000)
        self._logger.debug(
            "prompt_guard judge verdict",
            request_id=request_id, verdict=out.verdict, latency_ms=latency_ms,
        )
        return JudgeVerdict(
            verdict=out.verdict, reason=out.reason, latency_ms=latency_ms
        )

    async def _resolve_chain(self):
        """호출 시점의 관리자 모델로 체인을 만든다 (AD-2). 인스턴스가 같으면 재사용."""
        llm = await self._provider.get(self._temperature)
        if llm is None:
            raise JudgeUnavailableError("utility llm provider resolved no model")
        if llm is not self._cached_llm:
            self._cached_llm = llm
            self._cached_chain = self._prompt | llm.with_structured_output(
                InjectionJudgeOutput
            )
        return self._cached_chain
