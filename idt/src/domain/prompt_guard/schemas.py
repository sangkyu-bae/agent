"""prompt-guard 도메인 VO — Design Ref: §3.1.

규칙·판정·결정을 표현하는 불변 값 객체. LLM 출력 신뢰 경계(위키)에 따라
계산 필드(latency·rule_ids·hash)는 코드가 채우며 LLM 스키마에는 두지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GuardTier(str, Enum):
    """규칙 단계 또는 최종 판정 등급. BLOCK > REVIEW > PASS."""

    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class InputSource(str, Enum):
    """검사 대상 입력의 출처 (FR-14). 이번 사이클은 USER_CHAT 만 구현."""

    USER_CHAT = "user_chat"


class RuleCategory(str, Enum):
    OVERRIDE = "override"            # 지시 덮어쓰기
    ROLE_HIJACK = "role_hijack"      # 역할 탈취 (Design D1: REVIEW)
    PROMPT_LEAK = "prompt_leak"      # 시스템 프롬프트 유출 요구
    FAKE_DELIMITER = "fake_delimiter"  # 가짜 시스템 구분자
    JAILBREAK_TOKEN = "jailbreak"    # 알려진 탈옥 토큰
    SOFT_SIGNAL = "soft"             # 약한 신호 → REVIEW


@dataclass(frozen=True)
class GuardRule:
    """규칙 카탈로그 항목 (FR-15). pattern 은 정규화된 텍스트를 대상으로 한다."""

    id: str
    category: RuleCategory
    lang: str
    pattern: str
    tier: GuardTier


@dataclass(frozen=True)
class RuleMatch:
    rule_id: str
    category: RuleCategory
    tier: GuardTier


@dataclass(frozen=True)
class JudgeVerdict:
    verdict: str          # "injection" | "benign"
    reason: str
    latency_ms: int


@dataclass(frozen=True)
class GuardDecision:
    """최종 결정. `enforced` 가 True 일 때만 유스케이스가 차단한다 (Design D3)."""

    tier: GuardTier
    enforced: bool
    rule_ids: tuple[str, ...]
    judge: JudgeVerdict | None
    judge_error: str | None
    input_len: int
    input_hash12: str
    source: InputSource

    @property
    def summary(self) -> str:
        """스텝·로그용 1줄 (Design OQ5: 원문 없음)."""
        if self.judge is not None:
            judge = self.judge.verdict
        else:
            judge = self.judge_error or "skipped"
        rules = ",".join(self.rule_ids) or "-"
        return (
            f"tier={self.tier.value} enforced={str(self.enforced).lower()} "
            f"rules={rules} judge={judge}"
        )
