"""근거 판정 도메인 — 판정 결과 VO 와 판정기 포트.

Design Ref: draft-grounding-check v0.2 §3.1.

기존 HallucinationEvaluator 는 참/거짓만 돌려줘 "무엇을 고칠지" 알 수 없었다.
근거 판정기는 생성문에서 근거 없는 **주장 구간**을 원문 그대로 인용해 돌려주고,
재작성 루프가 그 구간을 사유로 넣어 다시 쓰게 한다.
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from src.domain.hallucination.value_objects import HallucinationEvaluationResult

# 근거 재작성 루프 안의 LLM 호출(생성·판정·재작성)에 붙이는 태그.
# 채팅 토큰 스트림은 이 태그가 붙은 이벤트를 내보내지 않는다(Design §2.3, D-04).
INTERNAL_LLM_TAG = "grounding_internal"

Severity = Literal["high", "low"]

# 판정 구간 앞의 목록 기호("- ", "1. ")와 짧은 라벨("제목: ")은 값이 아니다.
_LIST_MARKER = re.compile(r"^\s*(?:[-*•·]|\d+[.)])\s*")
_LABEL = re.compile(r"^[^:：\n]{1,12}[:：]\s*")
_MIN_LITERAL_CHARS = 2


@dataclass(frozen=True)
class UnsupportedClaim:
    span: str  # 생성문 원문 그대로의 구간 — 문장 제거 기준
    reason: str
    severity: Severity


@dataclass(frozen=True)
class GroundingVerdict:
    unsupported_claims: tuple[UnsupportedClaim, ...]

    @property
    def grounded(self) -> bool:
        return not self.unsupported_claims

    @property
    def high_claims(self) -> tuple[UnsupportedClaim, ...]:
        """재작성 대상 — 고객이 그대로 행동하게 되는 근거 없는 사실 (D-05)."""
        return tuple(c for c in self.unsupported_claims if c.severity == "high")

    def excluding_found_in(self, sources: str) -> "GroundingVerdict":
        """근거에 글자 그대로(공백 차이 무시) 있는 주장을 뺀다 — 판정기 오판 보정.

        L3 실측: 판정기가 조회 결과에 그대로 있는 상품명·제목을 '근거 없음' 으로
        판정해 정상 문장이 지워졌다. 원문 그대로 있으면 정의상 근거가 있으므로
        주장을 줄이기만 한다(늘리지 않는다) — 과삭제 위험 없음.
        """
        corpus = " ".join((sources or "").split())
        kept = tuple(c for c in self.unsupported_claims if not _found_literally(c.span, corpus))
        return self if len(kept) == len(self.unsupported_claims) else GroundingVerdict(kept)


def _found_literally(span: str, corpus: str) -> bool:
    core = _LABEL.sub("", _LIST_MARKER.sub("", span or ""), count=1)
    core = " ".join(core.split())
    return len(core) >= _MIN_LITERAL_CHARS and core in corpus


class GroundingJudgePort(ABC):
    """근거 판정기 포트 — infrastructure 어댑터가 LLM 으로 구현한다."""

    @abstractmethod
    async def judge(
        self, *, question: str, sources: str, generation: str,
        hints: list[str], request_id: str,
    ) -> GroundingVerdict:
        """근거 없는 주장 목록. 실패는 예외로 올린다(fail-open 은 호출측 몫)."""


class HallucinationEvaluatorPort(ABC):
    """기존 참/거짓 판정 포트 (D-08: use case 의 infrastructure 직접 참조 정리)."""

    @abstractmethod
    async def evaluate(
        self, documents: list[str], generation: str, request_id: str,
    ) -> HallucinationEvaluationResult:
        """생성문이 문서에 근거하지 않으면 is_hallucinated=True."""
