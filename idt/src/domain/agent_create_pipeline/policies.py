"""PipelinePolicy — 파이프라인 진행 규칙 (순수 함수, Design §3.3).

흐름(UseCase)과 규칙을 분리한다: 여기 있는 규칙은 LLM 목 없이 테스트되고,
후속 R1 수렴(기존 자동 생성 경로를 파이프라인으로 교체)에서 재사용된다.

degraded 판정 원칙은 위키 `degradation-vs-failure-boundary` 를 따른다 —
"쓸 수 있는 결과가 존재하는가". 여기서는 그 판정에 필요한 순수 계산만 한다.
"""
from collections.abc import Sequence
from typing import Literal

from src.domain.agent_create_pipeline.spec import PURPOSE_SLOT_KEY
from src.domain.agent_create_pipeline.stages import (
    STAGE_ORDER,
    StageRecord,
    StageStatus,
)
from src.domain.intent.schemas import IntentResult
from src.domain.tool_selection.schemas import SelectionResult

_FALLBACK_NAME = "새 에이전트"


class PipelinePolicy:
    """단계 전이·병합·폴백 판정. 전부 정적 순수 함수다."""

    PROMPT_MAX_CHARS = 4000
    """CreateAgentRequest.system_prompt 상한 (agent_builder 스키마 계약)."""

    NAME_MAX_CHARS = 200
    NAME_PREVIEW_CHARS = 30

    @staticmethod
    def decide_after_intent(result: IntentResult) -> Literal["ask", "proceed"]:
        """되묻기 분기 (FR-02/FR-07).

        degraded 는 무조건 proceed — 판정 실패는 되묻기 불능이며, "의도 모름"
        으로 진행하는 것이 계약이다. 질문 없는 미충족도 proceed — 물을 것이
        없는 왕복은 무한 루프가 된다.
        """
        if result.degraded or result.complete:
            return "proceed"
        if not result.questions:
            return "proceed"
        return "ask"

    @staticmethod
    def build_selector_query(
        user_request: str, result: IntentResult | None
    ) -> str:
        """도구 추천 질의 — 요청 원문 + 채워진 축 요약 (Design §2.2).

        degraded 판정의 슬롯은 신뢰하지 않는다 (LLM 출력 신뢰 경계 —
        오염값을 추천 근거로 쓰면 안 된다).
        """
        if result is None or result.degraded or not result.filled_slots:
            return user_request
        lines = [f"{key}: {value}" for key, value in result.filled_slots.items()]
        return user_request + "\n" + "\n".join(lines)

    @staticmethod
    def resolve_tool_ids(selection: SelectionResult) -> tuple[str, ...]:
        """final_ids 를 그대로 신뢰한다 — required ⊆ final 은 포트 계약이다."""
        return selection.final_ids

    @staticmethod
    def empty_candidate_selection(
        user_ids: Sequence[str],
    ) -> SelectionResult:
        """후보 0건일 때의 강하 결과 — 셀렉터(LLM) 호출 없이 만든다.

        사용자 지정 도구만으로 진행한다 (순서 보존 dedupe). 후보가 없다는
        사실은 fallback=True 로 관측 가능해야 한다 (steps.tools=degraded).
        """
        deduped = tuple(dict.fromkeys(user_ids))
        return SelectionResult(
            selected_ids=(),
            required_ids=deduped,
            final_ids=deduped,
            candidate_count=0,
            fallback=True,
            reason="활성 도구 후보가 없어 추천을 건너뜀",
        )

    @staticmethod
    def resolve_agent_name(
        explicit: str | None,
        result: IntentResult | None,
        user_request: str,
    ) -> str:
        """이름 우선순위: 명시 > purpose 슬롯 > 요청 앞 30자 (Design §3.3)."""
        name = (explicit or "").strip()
        if not name and result is not None and not result.degraded:
            name = result.filled_slots.get(PURPOSE_SLOT_KEY, "").strip()
        if not name:
            name = " ".join(user_request.split())[
                : PipelinePolicy.NAME_PREVIEW_CHARS
            ]
        return name[: PipelinePolicy.NAME_MAX_CHARS] or _FALLBACK_NAME

    @staticmethod
    def clamp_prompt(assembled: str) -> tuple[str, str | None]:
        """system_prompt 4000자 clamp. 절단 시 사유를 돌려 steps 에 남긴다."""
        if len(assembled) <= PipelinePolicy.PROMPT_MAX_CHARS:
            return assembled, None
        reason = (
            f"프롬프트 {len(assembled)}자 → "
            f"{PipelinePolicy.PROMPT_MAX_CHARS}자 절단"
        )
        return assembled[: PipelinePolicy.PROMPT_MAX_CHARS], reason

    @staticmethod
    def finalize_steps(
        records: Sequence[StageRecord], skip_reason: str
    ) -> tuple[StageRecord, ...]:
        """미도달 단계를 skipped 로 채워 항상 5단계 전체를 반환한다 (§4.3).

        화면이 단계 바를 고정 렌더할 수 있게 하는 계약이다.
        """
        by_stage = {record.stage: record for record in records}
        return tuple(
            by_stage.get(
                stage,
                StageRecord(stage, StageStatus.SKIPPED, reason=skip_reason),
            )
            for stage in STAGE_ORDER
        )

    @staticmethod
    def clamp_round(round_: int, max_rounds: int) -> int:
        """클라이언트 신고 round 재clamp — stateless-hitl 위키 패턴."""
        return max(0, min(round_, max_rounds))
