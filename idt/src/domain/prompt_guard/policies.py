"""prompt-guard 정책 — Design Ref: §3.3·§3.4.

- NormalizationPolicy: 우회(zero-width·전각·대소문자·공백) 제거 (FR-01)
- PromptGuardPolicy: 규칙 매치·tier 결정·판정기 입력 절단·최종 결정 (FR-02/03/11)
- BlockedTurnPolicy: 차단 턴을 LLM 컨텍스트 조립에서 제외 (OQ2)
- BLOCK_NOTICE_KO: 결정적 안내문 (FR-08, OQ3)
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Sequence

from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.value_objects import MessageRole
from src.domain.prompt_guard.schemas import (
    GuardDecision,
    GuardRule,
    GuardTier,
    InputSource,
    JudgeVerdict,
    RuleMatch,
)

# Design §3.4 (OQ3) — LLM 생성 금지, 상수 하나.
# BlockedTurnPolicy 가 이 값으로 차단 턴을 식별한다.
BLOCK_NOTICE_KO = (
    "요청하신 내용은 이 에이전트의 운영 지침과 충돌해 처리할 수 없습니다. "
    "지침을 변경하거나 공개하라는 요청은 수행하지 않으며, "
    "다른 질문은 계속 도와드릴 수 있습니다."
)

GUARD_MODES: frozenset[str] = frozenset({"block", "log_only"})

# zero-width·BOM·soft hyphen 등 비가시 문자 (개행·탭은 공백 축약 단계에서 처리)
_INVISIBLE = re.compile(r"[​-‏⁠﻿­]")
_WHITESPACE = re.compile(r"\s+")
_TIER_RANK = {GuardTier.PASS: 0, GuardTier.REVIEW: 1, GuardTier.BLOCK: 2}


class NormalizationPolicy:
    """FR-01: 원문은 바꾸지 않고 규칙 적용용 정규화 사본을 만든다."""

    @staticmethod
    def normalize(text: str) -> str:
        out = unicodedata.normalize("NFKC", text).casefold()
        out = _INVISIBLE.sub("", out)
        out = "".join(
            ch for ch in out
            if ch.isspace() or unicodedata.category(ch) != "Cc"
        )
        return _WHITESPACE.sub(" ", out).strip()


class PromptGuardPolicy:
    """규칙 적용·tier·판정 입력 절단·최종 결정. 상태는 컴파일된 규칙만."""

    def __init__(self, rules: Sequence[GuardRule]) -> None:
        self._rules = [
            (rule, re.compile(rule.pattern, re.IGNORECASE | re.MULTILINE))
            for rule in rules
        ]

    def match(self, normalized: str) -> list[RuleMatch]:
        return [
            RuleMatch(rule.id, rule.category, rule.tier)
            for rule, compiled in self._rules
            if compiled.search(normalized)
        ]

    @staticmethod
    def tier_of(matches: Sequence[RuleMatch]) -> GuardTier:
        """BLOCK > REVIEW > PASS."""
        if not matches:
            return GuardTier.PASS
        return max((m.tier for m in matches), key=_TIER_RANK.__getitem__)

    @staticmethod
    def head_tail(text: str, max_chars: int) -> str:
        """OQ4: 초과분은 머리/꼬리 절반씩 남기고 중간을 생략 표기로 대체."""
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        omitted = len(text) - 2 * half
        return f"{text[:half]}\n…[중간 {omitted}자 생략]…\n{text[-half:]}"

    @staticmethod
    def decide(
        *,
        tier: GuardTier,
        mode: str,
        matches: Sequence[RuleMatch],
        judge: JudgeVerdict | None,
        judge_error: str | None,
        text: str,
        source: InputSource,
    ) -> GuardDecision:
        """D3: 모드 적용은 여기서 끝난다. enforced 만 유스케이스가 본다."""
        return GuardDecision(
            tier=tier,
            enforced=(tier is GuardTier.BLOCK and mode == "block"),
            rule_ids=tuple(m.rule_id for m in matches),
            judge=judge,
            judge_error=judge_error,
            input_len=len(text),
            input_hash12=hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
            source=source,
        )


class BlockedTurnPolicy:
    """OQ2: 차단 턴(assistant == 안내문)과 직전 user 메시지를 컨텍스트에서 제외.

    저장·turn_index 계산용 원본 리스트는 건드리지 않는다 — 호출자는 반환값을
    **컨텍스트 조립에만** 쓰고 `len(원본)` 으로 turn 을 계산해야 한다 (Design §4.6).
    """

    NOTICE = BLOCK_NOTICE_KO

    @classmethod
    def is_block_notice(cls, message: ConversationMessage) -> bool:
        return (
            message.role is MessageRole.ASSISTANT
            and message.content.strip() == cls.NOTICE
        )

    @classmethod
    def exclude_blocked_turns(
        cls, messages: Sequence[ConversationMessage]
    ) -> list[ConversationMessage]:
        kept: list[ConversationMessage] = []
        # Check G-1: 에이전트 경로 기존 결함으로 user/assistant 가 같은 turn_index 를
        # 가질 수 있다 — tie 에서는 user 를 먼저 세워 안내문이 직전 user 를 찾게 한다.
        ordered = sorted(
            messages,
            key=lambda m: (m.turn_index.value, 0 if m.role is MessageRole.USER else 1),
        )
        for msg in ordered:
            if not cls.is_block_notice(msg):
                kept.append(msg)
                continue
            if kept and kept[-1].role is MessageRole.USER:
                kept.pop()
        return kept
