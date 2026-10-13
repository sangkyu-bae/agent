"""prompt-guard 포트 — Design Ref: §3.5.

- InjectionJudgePort: REVIEW 구간 LLM 판정 (infrastructure 구현). 공급자 미해석 시
  JudgeUnavailableError 을 raise 하고 서비스가 fail-open 한다 (D4).
- PromptGuardPort: 유스케이스가 의존하는 검사 진입점 (application 구현).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.prompt_guard.schemas import GuardDecision, InputSource, JudgeVerdict


@runtime_checkable
class InjectionJudgePort(Protocol):
    async def judge(self, text: str, *, request_id: str) -> JudgeVerdict:
        ...


@runtime_checkable
class PromptGuardPort(Protocol):
    async def inspect(
        self,
        text: str,
        *,
        source: InputSource = InputSource.USER_CHAT,
        request_id: str,
        user_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> GuardDecision:
        ...
