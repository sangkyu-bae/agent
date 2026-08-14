"""의도 판정 결과 검증·정규화 정책.

Design Ref: §2.2 — 판정 자체는 LLM 이 하되(Plan D2), 신뢰할 수 없는 출력을
도메인 계약에 맞추는 일은 순수 함수가 맡는다. LLM·IO 의존이 없으므로 분기를
100% 테스트할 수 있다 (Plan §4.2).
"""
from src.domain.intent.schemas import IntentResult, IntentSpec

_MIN_CONFIDENCE = 0.0
_MAX_CONFIDENCE = 1.0


class IntentResultPolicy:
    """LLM 원시 출력 → 도메인 계약을 만족하는 IntentResult."""

    @staticmethod
    def degraded() -> IntentResult:
        """판정을 시도조차 못 한 경우의 결과 (Plan D6 / Design E4~E6).

        '의도 모름'을 뜻하며, 호출자는 기존 로직을 그대로 진행하면 된다.
        """
        return IntentResult(degraded=True)

    @staticmethod
    def normalize(
        raw: IntentResult,
        spec: IntentSpec,
        *,
        degraded: bool = False,
    ) -> IntentResult:
        """LLM 출력을 spec 기준으로 검증·정규화한다.

        `raw.degraded` 는 **읽지 않는다** — LLM 이 채울 수 있는 값이므로
        호출자가 넘긴 `degraded` 인자만 신뢰한다 (Design §2.4 3층 방어).
        """
        label = _resolve_label(raw.label, spec)
        return IntentResult(
            label=label,
            confidence=_resolve_confidence(raw.confidence, label),
            entities=dict(raw.entities),
            ambiguous=_resolve_ambiguous(raw, label),
            missing_slots=_filter_slots(raw.missing_slots, spec.slots),
            reason=raw.reason,
            degraded=degraded,
        )


def _resolve_label(raw_label: str | None, spec: IntentSpec) -> str | None:
    """spec 에 없는 label 은 None 으로 강등한다 (Design E7)."""
    if not raw_label:
        return None
    known = {label.name for label in spec.labels}
    return raw_label if raw_label in known else None


def _resolve_confidence(raw_confidence: float, label: str | None) -> float:
    """label 이 없으면 0.0, 있으면 0.0~1.0 으로 clamp 한다 (Design E8)."""
    if label is None:
        return _MIN_CONFIDENCE
    return max(_MIN_CONFIDENCE, min(_MAX_CONFIDENCE, raw_confidence))


def _resolve_ambiguous(raw: IntentResult, label: str | None) -> bool:
    """강등된 경우에만 ambiguous 를 세운다.

    빈 label 은 '해당 없음' 탈출구(Design §4.3)이지 후보가 갈린 것이 아니므로
    ambiguous 로 승격하지 않는다.
    """
    demoted = bool(raw.label) and label is None
    return raw.ambiguous or demoted


def _filter_slots(raw_slots: list[str], requested: list[str]) -> list[str]:
    """요청되지 않은 슬롯 키는 버린다."""
    allowed = set(requested)
    return [slot for slot in raw_slots if slot in allowed]
