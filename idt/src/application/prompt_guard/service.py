"""PromptGuardService — Design Ref: §4.1 (흐름 제어·fail-open·로그).

normalize → rules → (REVIEW 면 판정기) → GuardDecision.
Plan SC: PASS 경로는 LLM 호출 0회. 판정기 장애는 PASS + warning (FR-06).
"""
from __future__ import annotations

import asyncio
import time

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.prompt_guard.exceptions import JudgeUnavailableError
from src.domain.prompt_guard.interfaces import InjectionJudgePort
from src.domain.prompt_guard.policies import (
    GUARD_MODES,
    NormalizationPolicy,
    PromptGuardPolicy,
)
from src.domain.prompt_guard.schemas import (
    GuardDecision,
    GuardTier,
    InputSource,
    JudgeVerdict,
)

_SNIPPET_MAX_CHARS = 200


class PromptGuardService:
    """PromptGuardPort 구현."""

    def __init__(
        self,
        *,
        policy: PromptGuardPolicy,
        judge: InjectionJudgePort | None,
        mode: str,
        judge_timeout_seconds: float,
        judge_max_chars: int,
        logger: LoggerInterface,
    ) -> None:
        if mode not in GUARD_MODES:
            raise ValueError(
                f"prompt_guard_mode must be one of {sorted(GUARD_MODES)}: {mode!r}"
            )
        self._policy = policy
        self._judge = judge
        self._mode = mode
        self._timeout = judge_timeout_seconds
        self._max_chars = judge_max_chars
        self._logger = logger

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
        matches = self._policy.match(NormalizationPolicy.normalize(text))
        tier = PromptGuardPolicy.tier_of(matches)
        verdict: JudgeVerdict | None = None
        judge_error: str | None = None
        if tier is GuardTier.REVIEW:
            tier, verdict, judge_error = await self._review(text, request_id)
        decision = PromptGuardPolicy.decide(
            tier=tier, mode=self._mode, matches=matches, judge=verdict,
            judge_error=judge_error, text=text, source=source,
        )
        if decision.tier is not GuardTier.PASS or verdict is not None or judge_error:
            self._log(decision, text, request_id, user_id, agent_id, session_id)
        return decision

    async def _review(
        self, text: str, request_id: str
    ) -> tuple[GuardTier, JudgeVerdict | None, str | None]:
        """REVIEW → 판정기. 실패는 전부 fail-open (FR-06, Design §6)."""
        if self._judge is None:
            return GuardTier.PASS, None, "judge_disabled"
        started = time.monotonic()
        try:
            verdict = await asyncio.wait_for(
                self._judge.judge(
                    PromptGuardPolicy.head_tail(text, self._max_chars),
                    request_id=request_id,
                ),
                timeout=self._timeout,
            )
        except TimeoutError as e:
            # Check G-4: logging 규칙 — 삼키는 예외도 exception= 으로 스택을 남긴다
            self._warn_judge(
                "prompt_guard judge timeout — fail-open", request_id, started, e
            )
            return GuardTier.PASS, None, "timeout"
        except JudgeUnavailableError as e:
            self._warn_judge(
                "prompt_guard judge unavailable — fail-open", request_id, started, e
            )
            return GuardTier.PASS, None, "unavailable"
        except Exception as e:  # noqa: BLE001 — 판정기 실패가 채팅을 죽이면 안 된다
            self._warn_judge(
                "prompt_guard judge failed — fail-open", request_id, started, e
            )
            return GuardTier.PASS, None, "exception"
        tier = GuardTier.BLOCK if verdict.verdict == "injection" else GuardTier.PASS
        return tier, verdict, None

    def _warn_judge(
        self,
        message: str,
        request_id: str,
        started: float,
        exc: Exception | None = None,
    ) -> None:
        kwargs: dict = {
            "request_id": request_id,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "timeout_seconds": self._timeout,
        }
        if exc is not None:
            kwargs["exception"] = exc
        self._logger.warning(message, **kwargs)

    def _log(
        self,
        decision: GuardDecision,
        text: str,
        request_id: str,
        user_id: str | None,
        agent_id: str | None,
        session_id: str | None,
    ) -> None:
        """FR-12: 구조화 로그. 원문 전체 금지 — 스니펫 200자·해시 12자만."""
        fields = {
            "request_id": request_id,
            "tier": decision.tier.value,
            "enforced": decision.enforced,
            "mode": self._mode,
            "rule_ids": list(decision.rule_ids),
            "judge_verdict": decision.judge.verdict if decision.judge else None,
            "judge_latency_ms": decision.judge.latency_ms if decision.judge else None,
            "judge_error": decision.judge_error,
            "input_len": decision.input_len,
            "input_hash12": decision.input_hash12,
            "source": decision.source.value,
            "user_id": user_id,
            "agent_id": agent_id,
            "session_id": session_id,
            "snippet": text[:_SNIPPET_MAX_CHARS],
        }
        if decision.tier is GuardTier.BLOCK or decision.judge_error:
            self._logger.warning("prompt_guard decision", **fields)
        else:
            self._logger.info("prompt_guard decision", **fields)
