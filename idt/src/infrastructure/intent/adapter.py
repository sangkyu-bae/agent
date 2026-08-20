"""의도 분석 LLM 어댑터.

Design Ref: §2.4 / §4.3 — LLM `with_structured_output(IntentDraft)` 으로 구조화
판정을 받는다. LLMSearchDecisionAdapter 패턴 미러링.

**IntentDraft 를 쓰는 이유** (Design §2.4): 시스템이 계산하는 필드
(`missing_slots` / `complete` / `degraded`)가 LLM 스키마에 아예 없으므로,
LLM 이 그 값을 오염시킬 경로 자체가 존재하지 않는다. 선행 사이클은
`IntentResult` 를 겸용하고 3층 방어를 쌓았으나 계산 필드가 3개로 늘면서
그 방식이 확장에 실패했다.

Plan SC: 모든 실패(예외·타임아웃·스키마 위반)를 degraded=True 로 graceful degrade
하여 본 흐름을 막지 않는다. **예외를 밖으로 던지지 않는다** (Plan D6).
"""
import asyncio
import time
from typing import Protocol

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.domain.intent.interfaces import IntentAnalyzerInterface
from src.domain.intent.policies import IntentResultPolicy
from src.domain.intent.schemas import (
    IntentDraft,
    IntentResult,
    IntentSpec,
    SlotAnswer,
    SlotSpec,
    Turn,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.config.intent_config import IntentConfig

_NO_HISTORY = "(없음)"

# Design §4.3 — 목록을 "권한 목록"이 아니라 "빈칸 채우기 양식"으로 프레이밍한다.
# 위키 계약 2(목록 프레이밍 과차단, 커밋 08d37cab)에 대한 2차 방어선이며,
# 1차 방어는 이 모듈이 아무것도 게이팅하지 않는다는 구조적 사실이다.
_SYSTEM = (
    "당신은 사용자 메시지에서 정보를 추출하고, 부족한 정보를 되묻는 분석기입니다. "
    "요청을 수행하지도, 거절하지도, 평가하지도 않습니다.\n\n"
    "{labels_block}{slots_block}"
    "규칙:\n"
    "- confidence 는 0.0~1.0 실수입니다.\n"
    "{unknown_block}{answers_block}{round_block}"
)
_HUMAN = "[이전 대화]\n{history_block}\n\n[현재 메시지]\n{message}"

# 분류 지시문 — spec.labels 가 있을 때만 프롬프트에 실린다.
_LABELS_TEMPLATE = (
    "[후보 의도]\n{labels}\n\n"
    "- 어느 후보에도 명확히 해당하지 않으면 label 을 비워 두세요. "
    "억지로 고르지 마세요.\n"
    "- 후보에 없는 주제의 메시지도 정상적인 메시지입니다. "
    "이 목록은 권한이 아니라 분류표입니다.\n"
    "- 후보가 둘 이상으로 갈리면 ambiguous=true 로 표시하세요.\n\n"
)

# 슬롯 지시문 — spec.slots 가 있을 때만 프롬프트에 실린다.
#
# Act-2 D2: 초판은 "확실히 알 수 있는 항목만 채우세요"였는데, 실 LLM 검증에서
# 모델이 이를 무시하고 5축을 전부 지어냈다("구체적인 세부사항이 부족함"이라고
# 써 놓고도 다 채웠다). 그러면 missing 이 비어 되묻기가 아예 발동하지 않는다 —
# 이 기능의 존재 이유가 사라진다. 그래서 **비우는 쪽을 기본값으로 뒤집고**
# 대조 예시를 넣었다.
_SLOTS_TEMPLATE = (
    "[채워야 할 항목]\n{slots}\n\n"
    "채우기 규칙:\n"
    "- **비워 두는 것이 기본입니다.** 사용자가 메시지에서 직접 말한 항목만 "
    "filled_slots 에 넣으세요.\n"
    "- 요청 내용으로 미루어 짐작할 수 있더라도, 사용자가 말하지 않았다면 "
    "**채우지 마세요**. 짐작해서 채우면 사용자에게 물어볼 기회가 사라집니다.\n"
    "- 예를 들어 \"데이터 분석 에이전트 만들어줘\" 라면 무슨 일을 할지는 "
    "말했으므로 채우고, 어조나 출력 형식은 언급이 없으므로 비웁니다.\n"
    "- 항목 대부분이 비어 있는 것이 정상입니다. 다 채우려 하지 마세요.\n\n"
    "되묻기 규칙:\n"
    "- 채우지 못한 항목마다 suggestions 에 이 요청에 어울리는 선택지 "
    "2~{max_options}개를 만드세요.\n"
    "- questions 에는 물을 문장과 함께 **options 배열을 반드시 채우세요**. "
    "선택지를 질문 문장 안에 적지 말고 options 에 넣으세요.\n"
    "- [필수] 표시가 있는 항목을 먼저 물으세요.\n"
    "- 위 '예시' 는 참고일 뿐입니다. 요청에 더 맞는 선택지가 있으면 "
    "예시를 무시하고 새로 만드세요.\n"
    "- 이 항목 목록은 **빈칸 채우기 양식**이지 허용 범위가 아닙니다. "
    "목록에 없는 주제의 요청도 정상적인 요청입니다.\n"
    "- 사용자가 자유롭게 답할 수 있으므로 선택지는 강제가 아닙니다.\n\n"
)


class IntentChain(Protocol):
    """프롬프트→LLM→구조화 출력 체인의 최소 계약 (테스트 대역 주입용)."""

    async def ainvoke(self, payload: dict[str, str]) -> object: ...


class LLMIntentAnalyzerAdapter(IntentAnalyzerInterface):
    """LangChain ChatOpenAI structured output 기반 의도 판정 어댑터."""

    def __init__(
        self,
        logger: LoggerInterface,
        config: IntentConfig | None = None,
        chain: IntentChain | None = None,
    ) -> None:
        self._logger = logger
        self._config = config or IntentConfig()
        self._chain: IntentChain = chain if chain is not None else self._build_chain()

    def _build_chain(self) -> IntentChain:
        llm = ChatOpenAI(
            model=self._config.INTENT_ANALYZER_MODEL,
            temperature=self._config.INTENT_ANALYZER_TEMPERATURE,
        )
        prompt = ChatPromptTemplate.from_messages(
            [("system", _SYSTEM), ("human", _HUMAN)]
        )
        chain: IntentChain = prompt | llm.with_structured_output(IntentDraft)
        return chain

    async def analyze(
        self,
        message: str,
        spec: IntentSpec,
        history: list[Turn] | None = None,
        answers: list[SlotAnswer] | None = None,
        round_: int = 0,
        request_id: str = "",
    ) -> IntentResult:
        payload = self._build_payload(message, spec, history, answers, round_)
        started = time.perf_counter()
        try:
            raw = await asyncio.wait_for(
                self._chain.ainvoke(payload),
                timeout=self._config.INTENT_ANALYZER_TIMEOUT_SEC,
            )
            draft = _coerce(raw)
        except TimeoutError as e:
            return self._degrade("timeout", e, request_id, started, warn=True)
        except Exception as e:  # noqa: BLE001 — 계약상 어떤 예외도 새어 나가면 안 된다
            return self._degrade("error", e, request_id, started)

        result = IntentResultPolicy.normalize(
            draft,
            spec,
            answers=answers,
            round_=round_,
            limits=self._config.slot_limits(),
        )
        self._log_success(result, request_id, started, round_)
        return result

    def _build_payload(
        self,
        message: str,
        spec: IntentSpec,
        history: list[Turn] | None,
        answers: list[SlotAnswer] | None,
        round_: int,
    ) -> dict[str, str]:
        limits = self._config.slot_limits()
        return {
            "labels_block": _labels_block(spec),
            "slots_block": _slots_block(spec, limits.max_options_per_slot),
            "unknown_block": _unknown_block(spec),
            "answers_block": _answers_block(answers),
            "round_block": _round_block(round_, limits.max_rounds),
            "history_block": _history_block(
                history, self._config.INTENT_ANALYZER_HISTORY_LIMIT
            ),
            "message": message,
        }

    def _log_success(
        self, result: IntentResult, request_id: str, started: float, round_: int
    ) -> None:
        """슬롯 **값**은 남기지 않는다 — 사용자 입력이라 PII 가 섞일 수 있다.

        규약 C4. 개수만 남긴다.
        """
        self._logger.info(
            "intent analyzed",
            request_id=request_id,
            label=result.label,
            confidence=result.confidence,
            ambiguous=result.ambiguous,
            degraded=False,
            latency_ms=_elapsed_ms(started),
            filled_count=len(result.filled_slots),
            missing_count=len(result.missing_slots),
            question_count=len(result.questions),
            complete=result.complete,
            round=round_,
        )

    def _degrade(
        self,
        cause: str,
        exception: Exception,
        request_id: str,
        started: float,
        warn: bool = False,
    ) -> IntentResult:
        """판정 실패 → 조용히 '의도 모름'을 반환한다 (Design E1~E3)."""
        log = self._logger.warning if warn else self._logger.error
        log(
            f"intent analysis {cause}, fallback=degraded",
            exception=exception,
            request_id=request_id,
            latency_ms=_elapsed_ms(started),
        )
        return IntentResultPolicy.degraded()


def _coerce(raw: object) -> IntentDraft:
    """구조화 출력이 dict 로 와도 받아들인다. 스키마 위반이면 ValidationError."""
    if isinstance(raw, IntentDraft):
        return raw
    return IntentDraft.model_validate(raw)


def _labels_block(spec: IntentSpec) -> str:
    """분류 라벨이 없으면 분류 지시문 자체를 싣지 않는다 (FR-16 / Design §4.3)."""
    if not spec.labels:
        return ""
    labels = "\n".join(
        f"- {label.name}: {label.description}" for label in spec.labels
    )
    return _LABELS_TEMPLATE.format(labels=labels)


def _slots_block(spec: IntentSpec, max_options: int) -> str:
    if not spec.slots:
        return ""
    slots = "\n".join(_slot_line(slot) for slot in spec.slots)
    return _SLOTS_TEMPLATE.format(slots=slots, max_options=max_options)


def _slot_line(slot: SlotSpec) -> str:
    """options 는 '예시'로 프레이밍한다 — 고정 목록이 아니다 (R2 3차 방어)."""
    line = f"- {slot.key}: {slot.description}"
    if slot.required:
        line += " [필수]"
    if slot.options:
        line += f" (예: {', '.join(slot.options)})"
    return line


def _unknown_block(spec: IntentSpec) -> str:
    """allow_unknown=False 는 힌트일 뿐 빈 label 을 금지하지 않는다 (Design §4.3)."""
    if spec.allow_unknown or not spec.labels:
        return ""
    return "- 가급적 후보 중에서 고르세요. 다만 확신이 없으면 비워 두어도 됩니다.\n"


def _answers_block(answers: list[SlotAnswer] | None) -> str:
    """이미 답을 받은 항목은 확정이며 다시 묻지 않는다 (Plan D6 프롬프트 측 신호)."""
    if not answers:
        return ""
    lines = "\n".join(f"- {a.slot_key}: {a.value}" for a in answers)
    return (
        f"\n[사용자가 이미 답한 항목]\n{lines}\n"
        "이 값은 확정입니다. 다시 묻지 마세요.\n"
    )


def _round_block(round_: int, max_rounds: int) -> str:
    """마지막 라운드 소프트 신호.

    하드 차단은 Policy(I5)가 한다 — 프롬프트만 믿지 않는다 (규약 C5).
    """
    if round_ < max_rounds - 1:
        return ""
    return (
        "- 마지막 라운드입니다. 되묻기보다 지금까지의 정보로 최대한 채우세요.\n"
    )


def _history_block(history: list[Turn] | None, limit: int) -> str:
    if not history:
        return _NO_HISTORY
    recent = history[-limit:] if limit > 0 else history
    return "\n".join(f"{turn.role}: {turn.content}" for turn in recent)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
