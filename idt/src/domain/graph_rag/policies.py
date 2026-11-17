"""graph_rag 도메인 정책.

Design Ref: graph-rag-foundation §3.1·§4.2 — 노출 판단(RolloutPolicy)과 단계 전환
조건(StageTransitionPolicy). 둘 다 순수 함수라 저장소·라우터와 무관하게 테스트한다.
"""

from __future__ import annotations

from src.domain.graph_rag.exceptions import GraphStageEvalRequiredError
from src.domain.graph_rag.value_objects import RolloutStage

FORCE_REASON_MIN_LEN = 10
_AURA_HOST_SUFFIX = ".databases.neo4j.io"


def is_external_graph_uri(uri: str | None) -> bool:
    """Aura(외부 관리형 클라우드) 주소인지.

    관리자 화면 '외부 저장' 표시용 (Design §7).
    """
    if not uri or "://" not in uri:
        return False
    host = uri.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0].lower()
    return host.endswith(_AURA_HOST_SUFFIX)


class RolloutPolicy:
    """노출 단계 × 호출자 역할 → 실행·노출 허용 (Plan FR-20 의 '단계' 축)."""

    @staticmethod
    def skip_reason(stage: RolloutStage, *, caller_is_admin: bool) -> str | None:
        if stage is RolloutStage.OFF:
            return "stage_off"
        if stage is RolloutStage.ADMIN_ONLY and not caller_is_admin:
            return "grant_not_admin"
        return None

    @classmethod
    def allows(cls, stage: RolloutStage, *, caller_is_admin: bool) -> bool:
        return cls.skip_reason(stage, caller_is_admin=caller_is_admin) is None


class StageTransitionPolicy:
    """general(일반 공개) 전환은 RAGAS on/off 근거 또는 충분한 강제 사유가 필요."""

    @staticmethod
    def is_noop(current: RolloutStage, target: RolloutStage) -> bool:
        return current is target

    @staticmethod
    def validate(
        current: RolloutStage,
        target: RolloutStage,
        *,
        eval_evidence_ok: bool,
        force_reason: str | None,
    ) -> None:
        if target is not RolloutStage.GENERAL:
            return
        if eval_evidence_ok:
            return
        if force_reason and len(force_reason.strip()) >= FORCE_REASON_MIN_LEN:
            return
        raise GraphStageEvalRequiredError(
            "general 전환에는 RAGAS on/off 실행 2건 또는 "
            f"{FORCE_REASON_MIN_LEN}자 이상의 강제 사유가 필요합니다"
        )
