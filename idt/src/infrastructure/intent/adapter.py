"""의도 분석 LLM 어댑터.

Design Ref: §2.4 / §4.3 — LLM `with_structured_output(IntentResult)` 으로 구조화
판정을 받는다. LLMSearchDecisionAdapter 패턴 미러링.

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
from src.domain.intent.schemas import IntentResult, IntentSpec, Turn
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.config.intent_config import IntentConfig

_NO_HISTORY = "(없음)"

# Design §4.3 — 라벨 목록을 "권한 목록"이 아니라 "분류표"로 프레이밍한다.
# 위키 계약 2(목록 프레이밍 과차단, 커밋 08d37cab)에 대한 2차 방어선이며,
# 1차 방어는 이 모듈이 아무것도 게이팅하지 않는다는 구조적 사실이다.
_SYSTEM = (
    "당신은 사용자 메시지를 분류하는 분석기입니다. "
    "요청을 수행하지도, 거절하지도 않습니다. "
    "오직 아래 후보 중 어느 것에 해당하는지만 판단합니다.\n\n"
    "[후보]\n{labels_block}\n\n"
    "규칙:\n"
    "- 어느 후보에도 명확히 해당하지 않으면 label 을 비워 두세요. "
    "억지로 고르지 마세요.\n"
    "- 후보에 없는 주제의 메시지도 정상적인 메시지입니다. "
    "이 목록은 권한이 아니라 분류표입니다.\n"
    "- 후보가 둘 이상으로 갈리면 ambiguous=true 로 표시하세요.\n"
    "- confidence 는 0.0~1.0 실수입니다.\n"
    "- degraded 는 시스템이 채웁니다. 항상 false 로 두세요.\n"
    "{unknown_block}{slots_block}"
)
_HUMAN = "[이전 대화]\n{history_block}\n\n[현재 메시지]\n{message}"


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
        chain: IntentChain = prompt | llm.with_structured_output(IntentResult)
        return chain

    async def analyze(
        self,
        message: str,
        spec: IntentSpec,
        history: list[Turn] | None = None,
        request_id: str = "",
    ) -> IntentResult:
        payload = self._build_payload(message, spec, history)
        started = time.perf_counter()
        try:
            raw = await asyncio.wait_for(
                self._chain.ainvoke(payload),
                timeout=self._config.INTENT_ANALYZER_TIMEOUT_SEC,
            )
            parsed = _coerce(raw)
        except TimeoutError as e:
            return self._degrade("timeout", e, request_id, started, warn=True)
        except Exception as e:  # noqa: BLE001 — 계약상 어떤 예외도 새어 나가면 안 된다
            return self._degrade("error", e, request_id, started)

        result = IntentResultPolicy.normalize(parsed, spec)
        self._logger.info(
            "intent analyzed",
            request_id=request_id,
            label=result.label,
            confidence=result.confidence,
            ambiguous=result.ambiguous,
            degraded=False,
            latency_ms=_elapsed_ms(started),
        )
        return result

    def _build_payload(
        self, message: str, spec: IntentSpec, history: list[Turn] | None
    ) -> dict[str, str]:
        return {
            "labels_block": _labels_block(spec),
            "slots_block": _slots_block(spec),
            "unknown_block": _unknown_block(spec),
            "history_block": _history_block(
                history, self._config.INTENT_ANALYZER_HISTORY_LIMIT
            ),
            "message": message,
        }

    def _degrade(
        self,
        cause: str,
        exception: Exception,
        request_id: str,
        started: float,
        warn: bool = False,
    ) -> IntentResult:
        """판정 실패 → 조용히 '의도 모름'을 반환한다 (Design E4~E6)."""
        log = self._logger.warning if warn else self._logger.error
        log(
            f"intent analysis {cause}, fallback=degraded",
            exception=exception,
            request_id=request_id,
            latency_ms=_elapsed_ms(started),
        )
        return IntentResultPolicy.degraded()


def _coerce(raw: object) -> IntentResult:
    """구조화 출력이 dict 로 와도 받아들인다. 스키마 위반이면 ValidationError."""
    if isinstance(raw, IntentResult):
        return raw
    return IntentResult.model_validate(raw)


def _labels_block(spec: IntentSpec) -> str:
    return "\n".join(f"- {label.name}: {label.description}" for label in spec.labels)


def _slots_block(spec: IntentSpec) -> str:
    if not spec.slots:
        return ""
    keys = ", ".join(spec.slots)
    return (
        f"- entities 에 다음 키를 가능한 만큼 채우세요: {keys}. "
        "값을 찾지 못한 키는 missing_slots 에 넣으세요.\n"
    )


def _unknown_block(spec: IntentSpec) -> str:
    """allow_unknown=False 는 힌트일 뿐 빈 label 을 금지하지 않는다 (Design §4.3)."""
    if spec.allow_unknown:
        return ""
    return "- 가급적 후보 중에서 고르세요. 다만 확신이 없으면 비워 두어도 됩니다.\n"


def _history_block(history: list[Turn] | None, limit: int) -> str:
    if not history:
        return _NO_HISTORY
    recent = history[-limit:] if limit > 0 else history
    return "\n".join(f"{turn.role}: {turn.content}" for turn in recent)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
