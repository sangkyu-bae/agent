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
    PipelineStage,
    PipelineStop,
    StageRecord,
    StageStatus,
)
from src.domain.intent.schemas import IntentResult, IntentSpec
from src.domain.tool_selection.schemas import SelectionResult

_FALLBACK_NAME = "새 에이전트"

# agent-create-wizard §3.2 — 정지 지점 → 응답 status 매핑 (wire 계약).
_STOP_STATUS: dict[PipelineStop, str] = {
    PipelineStop.TOOLS: "tools_proposed",
    PipelineStop.PROMPT: "prompt_ready",
}


class PipelinePolicy:
    """단계 전이·병합·폴백 판정. 전부 정적 순수 함수다."""

    PROMPT_MAX_CHARS = 8000
    """CreateAgentRequest.system_prompt 상한 (agent_builder 스키마 계약).

    prompt-depth FR-21 — 4000 → 8000. 이 값이 `MAX_ASSEMBLED_CHARS`(응답 스키마)
    및 Create/Update 요청 스키마와 어긋나면 사용자는 **마지막 저장 단계에서**
    422 를 만난다. 4곳의 일치는 테스트가 강제한다 (Plan R-08).
    """

    NAME_MAX_CHARS = 200
    NAME_PREVIEW_CHARS = 30

    SLOT_VALUE_MAX_CHARS = 200
    """클라이언트 에코백 슬롯값 상한 (agent-create-wizard §3.2 / D2).

    intent 모듈은 슬롯값 길이를 제한하지 않는다 — LLM 출력이라 사실상 짧기
    때문이다. 그러나 에코백은 클라이언트가 만든 입력이므로 상한이 필요하다.
    """

    @staticmethod
    def decide_after_intent(
        result: IntentResult, round_: int = 0, max_rounds: int = 0
    ) -> Literal["ask", "proceed"]:
        """되묻기 분기 (FR-02/FR-07 · prompt-depth Act-1/G-01).

        degraded 는 무조건 proceed — 판정 실패는 되묻기 불능이며, "의도 모름"
        으로 진행하는 것이 계약이다. 질문 없는 미충족도 proceed — 물을 것이
        없는 왕복은 무한 루프가 된다.

        **complete 여도 한 번 더 묻는 경우** (prompt-depth G-01):
        이 스펙의 required 는 `purpose` 하나뿐이라(FR-16), round 1 에서 purpose
        가 채워지는 순간 complete 가 되어 되묻기가 끝났다. 그 결과 선언된 6축 중
        신규 2축(constraints/decision_priority)은 **한 번도 물어지지 않았고**,
        라운드 상한을 3으로 올린 FR-17 도 관측 가능한 효과가 없었다.

        구분 기준은 "이미 물어본 적이 있는가"다:
          · round 0 — 아직 아무것도 안 물었다. 사용자의 한 문장을 존중해 진행한다
            (SC-4: 상세히 쓴 요청은 되묻기 없이 통과). round 0 에서도 optional 축
            질문은 생성되므로, 이 가드가 없으면 상세 요청이 심문당한다.
          · round ≥ 1 — 이미 대화를 시작했다. 남은 선언 축을 마저 묻는 비용은
            왕복 1회이고, 그 자리에 LLM 이 추측하면 위험한 정보가 있다 (SC-3).

        기본 인자는 기존 호출부(round/max_rounds 미전달)의 의미를 보존한다.
        """
        if result.degraded:
            return "proceed"
        if not result.questions:
            return "proceed"
        if not result.complete:
            return "ask"
        if 1 <= round_ < max_rounds:
            return "ask"
        return "proceed"

    # ── 정지 지점 규칙 (agent-create-wizard §3.2) ───────────────────────

    @staticmethod
    def stages_to_run(stop: PipelineStop | None) -> tuple[PipelineStage, ...]:
        """intent 이후 실행할 단계 목록 (§3.2).

        `stop` 이 None 이면 `STAGE_ORDER[1:]` — 기존 논스톱 파이프라인의
        하드코딩 튜플과 **글자 그대로 동일**하다. 이 동일성이 FR-B09(회귀 0)를
        리뷰가 아니라 구조로 보장한다.
        """
        after_intent = STAGE_ORDER[1:]
        if stop is None:
            return after_intent
        end = after_intent.index(PipelineStage(stop.value)) + 1
        return after_intent[:end]

    @staticmethod
    def decide_after_stage(
        stage: PipelineStage, stop: PipelineStop | None
    ) -> Literal["stop", "continue"]:
        """이 단계 직후 멈출지 판정. `stop` 이 None 이면 항상 continue."""
        if stop is not None and stage.value == stop.value:
            return "stop"
        return "continue"

    @staticmethod
    def stop_status(stop: PipelineStop) -> str:
        """정지 지점 → 응답 status 문자열. 프론트가 분기하는 값이다."""
        return _STOP_STATUS[stop]

    @staticmethod
    def confirmed_selection(user_ids: Sequence[str]) -> SelectionResult:
        """사용자가 확정한 도구를 셀렉터 호출 없이 SelectionResult 로 (D1).

        **이것이 없으면 위저드가 성립하지 않는다**: 확정 후 재호출에서
        `_run_tools` 가 셀렉터를 다시 돌리면 `final_ids` 가
        `셀렉터출력 ∪ 확정목록` 이 되어 사용자가 제거한 도구가 되살아난다.

        `empty_candidate_selection` 과 달리 `fallback=False` 다 — 강하가 아니라
        "사람이 결정했으므로 추천이 불필요"한 정상 경로이기 때문이다.
        fallback=True 로 두면 steps.tools 가 degraded 로 칠해져 화면이
        "도구 추천 실패"로 오표시된다.
        """
        deduped = tuple(dict.fromkeys(user_ids))
        return SelectionResult(
            selected_ids=deduped,
            required_ids=deduped,
            final_ids=deduped,
            candidate_count=len(deduped),
            fallback=False,
            reason="사용자 확정 도구 — 추천 생략",
        )

    @staticmethod
    def reuse_intent(
        echo: IntentResult | None, spec: IntentSpec
    ) -> IntentResult | None:
        """클라이언트 에코백 의도를 spec 기준으로 재검증한다 (D2).

        재사용이 필요한 이유: 왕복마다 intent LLM 을 다시 돌리면 사용자가
        도구를 고른 근거였던 의도와 프롬프트 생성에 쓰인 의도가 달라질 수 있다.

        신뢰 경계 — 에코백은 클라이언트가 만든 입력이므로 그대로 믿지 않는다
        (stateless-hitl 의 "클라 신고값 재clamp" 와 같은 계열):
          · spec 에 없는 slot key 는 버린다
          · 값은 `SLOT_VALUE_MAX_CHARS` 로 clamp
          · degraded 로 신고된 에코백은 무시한다 — 실패를 영속시키지 않는다
          · `complete`/`missing_slots` 는 신고값을 쓰지 않고 **서버가 재계산**
            (llm-output-trust-boundary 를 클라이언트 입력에도 동일 적용)
          · `questions` 는 버린다 — 답을 받고 넘어온 단계에서 되묻기를
            다시 열면 위저드가 뒤로 돌아간다

        Returns:
            재사용 가능한 IntentResult, 또는 None(호출자가 intent 를 정상 실행).
        """
        if echo is None or echo.degraded:
            return None
        allowed = {slot.key for slot in spec.slots}
        filled = {
            key: value.strip()[: PipelinePolicy.SLOT_VALUE_MAX_CHARS]
            for key, value in echo.filled_slots.items()
            if key in allowed and value.strip()
        }
        if not filled:
            return None
        return IntentResult(
            label=echo.label,
            confidence=echo.confidence,
            ambiguous=echo.ambiguous,
            reason=echo.reason,
            filled_slots=filled,
            suggestions={},
            questions=[],
            missing_slots=[s.key for s in spec.slots if s.key not in filled],
            complete=all(s.key in filled for s in spec.slots if s.required),
            degraded=False,
        )

    # ── 기존 규칙 ───────────────────────────────────────────────────────

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
        """system_prompt 상한 clamp. 절단 시 사유를 돌려 steps 에 남긴다.

        사유 문구에 상한값을 포함하므로 상수만 바꾸면 안내도 따라 갱신된다.
        """
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
