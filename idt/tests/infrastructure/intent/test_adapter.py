"""LLMIntentAnalyzerAdapter 단위 테스트.

Design §8.2 시나리오 S25~S31 + 선행 사이클 시나리오 10~15.
실제 LLM 을 호출하지 않고 fake chain 을 주입한다.
핵심 계약: **어떤 실패도 예외로 새어 나가지 않는다** (Plan D6 / Design E1~E3).
"""
import asyncio
from typing import Any

import pytest
from src.domain.intent.schemas import (
    IntentDraft,
    IntentLabel,
    IntentSpec,
    SlotAnswer,
    SlotQuestionDraft,
    SlotSpec,
    Turn,
)
from src.infrastructure.config.intent_config import IntentConfig
from src.infrastructure.intent.adapter import LLMIntentAnalyzerAdapter


class RecordingLogger:
    """LoggerInterface 호환 스텁 — 호출 내역을 기록한다."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def debug(self, message: str, **kwargs: Any) -> None:
        self.calls.append(("debug", message, kwargs))

    def info(self, message: str, **kwargs: Any) -> None:
        self.calls.append(("info", message, kwargs))

    def warning(self, message: str, **kwargs: Any) -> None:
        self.calls.append(("warning", message, kwargs))

    def error(
        self, message: str, exception: Exception | None = None, **kwargs: Any
    ) -> None:
        self.calls.append(("error", message, {"exception": exception, **kwargs}))

    def critical(
        self, message: str, exception: Exception | None = None, **kwargs: Any
    ) -> None:
        self.calls.append(("critical", message, {"exception": exception, **kwargs}))

    def levels(self) -> list[str]:
        return [level for level, _, _ in self.calls]

    def kwargs_for(self, level: str) -> dict[str, Any]:
        for lvl, _, kwargs in self.calls:
            if lvl == level:
                return kwargs
        return {}


class FakeChain:
    """ainvoke 페이로드를 기록하고 정해진 반응을 돌려주는 fake."""

    def __init__(
        self,
        result: Any = None,
        raises: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self._result = result
        self._raises = raises
        self._delay = delay
        self.payloads: list[dict[str, Any]] = []

    async def ainvoke(self, payload: dict[str, Any]) -> Any:
        self.payloads.append(payload)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        return self._result


def _spec(slots: list[SlotSpec] | None = None) -> IntentSpec:
    return IntentSpec(
        labels=[
            IntentLabel(name="search", description="근거 문서를 찾아야 하는 질문"),
            IntentLabel(name="analysis", description="데이터를 계산·비교하는 질문"),
        ],
        slots=slots or [],
    )


def _slot(key: str, **kwargs: Any) -> SlotSpec:
    kwargs.setdefault("description", f"{key} 설명")
    return SlotSpec(key=key, **kwargs)


def _adapter(
    chain: FakeChain, timeout: float = 10.0, **config_kwargs: Any
) -> tuple[LLMIntentAnalyzerAdapter, RecordingLogger]:
    logger = RecordingLogger()
    config = IntentConfig(INTENT_ANALYZER_TIMEOUT_SEC=timeout, **config_kwargs)
    adapter = LLMIntentAnalyzerAdapter(logger=logger, config=config, chain=chain)
    return adapter, logger


# --- 정상 경로 --------------------------------------------------------------


async def test_successful_analysis_returns_normalized_result() -> None:
    chain = FakeChain(result=IntentDraft(label="search", confidence=0.82))
    adapter, logger = _adapter(chain)

    result = await adapter.analyze("여신 규정 알려줘", _spec())

    assert result.label == "search"
    assert result.confidence == pytest.approx(0.82)
    assert result.degraded is False
    assert "info" in logger.levels()


async def test_out_of_spec_label_is_demoted_not_degraded() -> None:
    """어댑터가 normalize 를 통과시키는지 확인 (Design E4)."""
    chain = FakeChain(result=IntentDraft(label="weather", confidence=0.9))
    adapter, _ = _adapter(chain)

    result = await adapter.analyze("내일 날씨", _spec())

    assert result.label is None
    assert result.ambiguous is True
    assert result.degraded is False


async def test_success_path_is_never_degraded() -> None:
    """IntentDraft 에 degraded 필드가 없으므로 LLM 이 오염시킬 경로가 없다 (§2.4)."""
    chain = FakeChain(result=IntentDraft(label="search", confidence=0.5))
    adapter, _ = _adapter(chain)

    result = await adapter.analyze("여신 규정", _spec())

    assert result.degraded is False


# --- S25: LLM 예외 (E1) -----------------------------------------------------


async def test_s25_chain_exception_returns_degraded_without_raising() -> None:
    chain = FakeChain(raises=RuntimeError("rate limit"))
    adapter, logger = _adapter(chain)

    result = await adapter.analyze("여신 규정", _spec(), request_id="req-1")

    assert result.degraded is True
    assert result.label is None
    assert result.confidence == pytest.approx(0.0)
    assert "error" in logger.levels()


async def test_chain_exception_logs_stack_trace_via_exception_kwarg() -> None:
    """error=str(e) 가 아니라 exception=e 로 기록해야 한다 (로깅 규약)."""
    boom = RuntimeError("boom")
    chain = FakeChain(raises=boom)
    adapter, logger = _adapter(chain)

    await adapter.analyze("여신 규정", _spec())

    assert logger.kwargs_for("error").get("exception") is boom


async def test_degraded_result_has_all_extension_fields_empty() -> None:
    """I6: 실패 시 확장 필드가 전부 비고 complete 는 False 다."""
    chain = FakeChain(raises=RuntimeError("boom"))
    adapter, _ = _adapter(chain)

    result = await adapter.analyze("여신 규정", _spec(slots=[_slot("tone")]))

    assert result.filled_slots == {}
    assert result.suggestions == {}
    assert result.questions == []
    assert result.missing_slots == []
    assert result.complete is False


# --- S26: 타임아웃 (E2) ------------------------------------------------------


async def test_s26_timeout_returns_degraded_with_warning() -> None:
    chain = FakeChain(result=IntentDraft(label="search"), delay=0.2)
    adapter, logger = _adapter(chain, timeout=0.01)

    result = await adapter.analyze("여신 규정", _spec())

    assert result.degraded is True
    assert "warning" in logger.levels()


# --- S27: 스키마 위반 (E3) ---------------------------------------------------


async def test_s27_schema_violation_returns_degraded() -> None:
    chain = FakeChain(result={"label": "search", "confidence": "높음"})
    adapter, _ = _adapter(chain)

    result = await adapter.analyze("여신 규정", _spec())

    assert result.degraded is True


async def test_dict_payload_matching_schema_is_accepted() -> None:
    """구조화 출력이 dict 로 와도 스키마를 만족하면 정상 처리한다."""
    chain = FakeChain(result={"label": "analysis", "confidence": 0.4})
    adapter, _ = _adapter(chain)

    result = await adapter.analyze("합계 계산해줘", _spec())

    assert result.label == "analysis"
    assert result.degraded is False


# --- history 처리 ------------------------------------------------------------


async def test_history_none_renders_placeholder() -> None:
    chain = FakeChain(result=IntentDraft(label="search"))
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec(), history=None)

    assert chain.payloads[0]["history_block"] == "(없음)"


async def test_history_is_truncated_to_configured_limit() -> None:
    chain = FakeChain(result=IntentDraft(label="search"))
    logger = RecordingLogger()
    config = IntentConfig(INTENT_ANALYZER_HISTORY_LIMIT=6)
    adapter = LLMIntentAnalyzerAdapter(logger=logger, config=config, chain=chain)
    history = [
        Turn(role="user" if i % 2 == 0 else "assistant", content=f"턴{i}")
        for i in range(20)
    ]

    await adapter.analyze("여신 규정", _spec(), history=history)

    block = chain.payloads[0]["history_block"]
    assert "턴19" in block
    assert "턴13" not in block, "최근 6턴(턴14~19)만 포함해야 한다"
    assert block.count("\n") == 5


# --- 프롬프트 조립: labels (Design §4.3) -------------------------------------


async def test_labels_block_contains_every_label_with_description() -> None:
    chain = FakeChain(result=IntentDraft(label="search"))
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec())

    block = chain.payloads[0]["labels_block"]
    assert "- search: 근거 문서를 찾아야 하는 질문" in block
    assert "- analysis: 데이터를 계산·비교하는 질문" in block


async def test_s28_labels_block_is_empty_for_slots_only_spec() -> None:
    """분류 라벨이 없으면 분류 지시문 자체를 싣지 않는다 (FR-16)."""
    spec = IntentSpec(slots=[_slot("tone")])
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain)

    await adapter.analyze("에이전트 만들어줘", spec)

    assert chain.payloads[0]["labels_block"] == ""


async def test_unknown_block_is_empty_when_unknown_allowed() -> None:
    chain = FakeChain(result=IntentDraft(label="search"))
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec())

    assert chain.payloads[0]["unknown_block"] == ""


async def test_unknown_block_nudges_but_does_not_forbid_empty_label() -> None:
    """allow_unknown=False 는 힌트일 뿐 빈 label 을 금지하지 않는다 (Design §4.3).

    억지 선택을 강제하면 위키 계약 2(목록 프레이밍 과차단)를 재현하기 때문이다.
    """
    spec = IntentSpec(
        labels=[
            IntentLabel(name="search", description="근거 문서를 찾아야 하는 질문"),
            IntentLabel(name="analysis", description="데이터를 계산·비교하는 질문"),
        ],
        allow_unknown=False,
    )
    chain = FakeChain(result=IntentDraft(label="search"))
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", spec)

    block = chain.payloads[0]["unknown_block"]
    assert block != "", "힌트 문구가 들어가야 한다"
    assert "비워 두어도" in block, "빈 label 을 금지하는 문구여선 안 된다"


# --- 프롬프트 조립: slots ----------------------------------------------------


async def test_slots_block_is_empty_when_no_slots_requested() -> None:
    chain = FakeChain(result=IntentDraft(label="search"))
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec())

    assert chain.payloads[0]["slots_block"] == ""


async def test_slots_block_lists_key_and_description() -> None:
    chain = FakeChain(result=IntentDraft(label="search"))
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec(slots=[_slot("기간"), _slot("대상")]))

    block = chain.payloads[0]["slots_block"]
    assert "- 기간: 기간 설명" in block
    assert "- 대상: 대상 설명" in block


async def test_slots_block_marks_required_slots() -> None:
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain)

    await adapter.analyze(
        "여신 규정", _spec(slots=[_slot("task", required=True), _slot("tone")])
    )

    block = chain.payloads[0]["slots_block"]
    assert "- task: task 설명 [필수]" in block
    assert "[필수]" not in block.split("\n")[2], "optional 축에는 표시하지 않는다"


async def test_slot_options_are_framed_as_examples() -> None:
    """options 는 고정 목록이 아니라 예시다 (R2 3차 방어)."""
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain)

    await adapter.analyze(
        "여신 규정", _spec(slots=[_slot("tone", options=["격식", "친근"])])
    )

    block = chain.payloads[0]["slots_block"]
    assert "(예: 격식, 친근)" in block
    assert "예시를 무시하고 새로 만드세요" in block


async def test_slots_block_frames_list_as_form_not_permission() -> None:
    """위키 계약 2 방어 문구가 프롬프트에 실려야 한다 (R2 2차 방어)."""
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec(slots=[_slot("tone")]))

    block = chain.payloads[0]["slots_block"]
    assert "빈칸 채우기 양식" in block
    assert "허용 범위가 아닙니다" in block


# --- S29: answers 블록 -------------------------------------------------------


async def test_s29_answers_block_is_empty_without_answers() -> None:
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec(slots=[_slot("tone")]))

    assert chain.payloads[0]["answers_block"] == ""


async def test_s29_answers_block_lists_confirmed_values() -> None:
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain)

    await adapter.analyze(
        "여신 규정",
        _spec(slots=[_slot("tone")]),
        answers=[SlotAnswer(slot_key="tone", value="친근")],
    )

    block = chain.payloads[0]["answers_block"]
    assert "[사용자가 이미 답한 항목]" in block
    assert "- tone: 친근" in block
    assert "다시 묻지 마세요" in block


async def test_answers_override_llm_extraction_end_to_end() -> None:
    """Plan D6 이 어댑터 경로에서도 성립하는지 확인한다."""
    chain = FakeChain(result=IntentDraft(filled_slots={"tone": "격식"}))
    adapter, _ = _adapter(chain)

    result = await adapter.analyze(
        "여신 규정",
        _spec(slots=[_slot("tone")]),
        answers=[SlotAnswer(slot_key="tone", value="친근")],
    )

    assert result.filled_slots == {"tone": "친근"}


# --- S30: round 블록 ---------------------------------------------------------


async def test_s30_round_block_is_empty_early() -> None:
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain, INTENT_MAX_CLARIFICATION_ROUNDS=3)

    await adapter.analyze("여신 규정", _spec(slots=[_slot("tone")]), round_=0)

    assert chain.payloads[0]["round_block"] == ""


async def test_s30_round_block_warns_on_last_round() -> None:
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain, INTENT_MAX_CLARIFICATION_ROUNDS=2)

    await adapter.analyze("여신 규정", _spec(slots=[_slot("tone")]), round_=1)

    assert "마지막 라운드" in chain.payloads[0]["round_block"]


async def test_round_cap_hard_blocks_questions_regardless_of_prompt() -> None:
    """프롬프트는 소프트 신호일 뿐 — Policy 가 하드 강제한다 (I5 / 규약 C5)."""
    chain = FakeChain(
        result=IntentDraft(
            questions=[SlotQuestionDraft(slot_key="tone", question="어조는?")]
        )
    )
    adapter, _ = _adapter(chain, INTENT_MAX_CLARIFICATION_ROUNDS=2)

    result = await adapter.analyze(
        "여신 규정", _spec(slots=[_slot("tone")]), round_=2
    )

    assert result.questions == []


# --- S31: 로그 필드 ----------------------------------------------------------


async def test_s31_success_log_carries_slot_counters() -> None:
    chain = FakeChain(
        result=IntentDraft(
            filled_slots={"tone": "친근"},
            questions=[SlotQuestionDraft(slot_key="task", question="무엇을?")],
        )
    )
    adapter, logger = _adapter(chain)

    await adapter.analyze(
        "여신 규정",
        _spec(slots=[_slot("tone"), _slot("task")]),
        request_id="req-9",
    )

    kwargs = logger.kwargs_for("info")
    assert kwargs["filled_count"] == 1
    assert kwargs["missing_count"] == 1
    assert kwargs["question_count"] == 1
    assert kwargs["complete"] is True
    assert kwargs["round"] == 0
    assert kwargs["request_id"] == "req-9"


async def test_s31_success_log_does_not_leak_slot_values() -> None:
    """슬롯 값은 사용자 입력이라 PII 가 섞일 수 있다 (규약 C4)."""
    chain = FakeChain(result=IntentDraft(filled_slots={"tone": "주민번호 900101"}))
    adapter, logger = _adapter(chain)

    await adapter.analyze("여신 규정", _spec(slots=[_slot("tone")]))

    assert "900101" not in str(logger.kwargs_for("info"))


# --- 상한 주입 (규약 C3) -----------------------------------------------------


async def test_config_limits_are_forwarded_to_policy() -> None:
    chain = FakeChain(
        result=IntentDraft(
            questions=[
                SlotQuestionDraft(slot_key=k, question=f"{k}?")
                for k in ("a", "b", "c")
            ]
        )
    )
    adapter, _ = _adapter(chain, INTENT_MAX_QUESTIONS_PER_ROUND=1)

    result = await adapter.analyze(
        "여신 규정", _spec(slots=[_slot("a"), _slot("b"), _slot("c")])
    )

    assert len(result.questions) == 1


async def test_max_options_is_rendered_into_prompt() -> None:
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain, INTENT_MAX_OPTIONS_PER_SLOT=5)

    await adapter.analyze("여신 규정", _spec(slots=[_slot("tone")]))

    assert "2~5개" in chain.payloads[0]["slots_block"]


# --- 프롬프트 안전성 ---------------------------------------------------------


async def test_braces_in_message_do_not_break_prompt_assembly() -> None:
    """사용자 메시지의 중괄호가 템플릿 포매팅을 깨뜨리지 않아야 한다."""
    chain = FakeChain(result=IntentDraft(label="search"))
    adapter, _ = _adapter(chain)

    result = await adapter.analyze("{여신} {{한도}} 규정", _spec())

    assert result.degraded is False
    assert chain.payloads[0]["message"] == "{여신} {{한도}} 규정"


# --- Act-2 D2: 과충전 방지 프롬프트 -----------------------------------------
#
# 실 LLM 검증에서 모델이 사용자가 말하지 않은 축까지 지어내 missing 이 비고
# 되묻기가 발동하지 않았다. 아래는 그 방어 문구가 프롬프트에서 사라지지 않도록
# 잠근다 — 문구가 빠지면 기능이 조용히 무력화된다.


async def test_d2_prompt_makes_leaving_blank_the_default() -> None:
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec(slots=[_slot("tone")]))

    block = chain.payloads[0]["slots_block"]
    assert "비워 두는 것이 기본입니다" in block
    assert "직접 말한 항목만" in block


async def test_d2_prompt_forbids_inference_filling() -> None:
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec(slots=[_slot("tone")]))

    block = chain.payloads[0]["slots_block"]
    assert "짐작" in block
    assert "물어볼 기회가 사라집니다" in block, "왜 안 되는지 이유를 줘야 한다"
    assert "다 채우려 하지 마세요" in block


async def test_d2_prompt_demands_options_array() -> None:
    """D1 의 프롬프트 측 대응 — Policy 폴백과 이중으로 막는다."""
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec(slots=[_slot("tone")]))

    block = chain.payloads[0]["slots_block"]
    assert "options 배열을 반드시 채우세요" in block
    assert "질문 문장 안에 적지 말고" in block


async def test_d2_prompt_prioritizes_required_axes() -> None:
    chain = FakeChain(result=IntentDraft())
    adapter, _ = _adapter(chain)

    await adapter.analyze("여신 규정", _spec(slots=[_slot("tone")]))

    assert "[필수] 표시가 있는 항목을 먼저" in chain.payloads[0]["slots_block"]
