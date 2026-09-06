"""collect 노드: 인자 생성 → 검증 → 도구 1회 호출 → 조건부 압축.

Design Ref: mcp-tool-category-routing §2.2 / §5 D-03 / §6.1

왜 search 노드를 재사용하지 않는가 (D-03):
  search 파이프라인은 `rewrite(질문→검색어) → search → validate → compress`이고
  도구를 `{"query": ...}`로 부른다(search_pipeline._safe_search). 수집형 도구에
  필요한 건 재작성된 검색어가 아니라 '대화에서 확정된 대상'(URL 등)이며,
  rewrite 단계는 오히려 ToolArgumentPolicy가 막고 있는 인자 환각을 유도한다.

왜 react(create_agent)가 아닌가 (§1.2):
  react 워커의 최종 산출은 LLM 종합문이다. 수집 워커가 분석까지 해버리면
  하류 analysis/final_answer 노드가 소비할 '근거'가 사라진다. 이 노드는
  도구 원본을 그대로 근거 규약에 실어 내보내고 분석은 하류에 남긴다.

시그니처·반환 계약은 create_search_pipeline_node / create_deep_search_node와
동일하다 (AD-1). 근거 메시지 규약은 search_pipeline이 단일 출처다 (D2).
"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from src.application.agent_builder.search_pipeline import (
    format_search_result,
    latest_user_question,
)
from src.application.agent_builder.supervisor_state import SupervisorState
from src.application.agent_run.step_tracking import STEP_OUTPUT_SUMMARY_KEY
from src.domain.agent_builder.policies import CollectPipelinePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy

# 대화 맥락 직렬화 한도 — search_pipeline과 같은 기준(D5).
_CONTEXT_MAX_MESSAGES = 6
_CONTEXT_MSG_SLICE = 500
_SUMMARY_MAX_CHARS = 512
# 인자 생성 프롬프트에 싣는 입력 스키마 최대 길이(자). 거대한 스키마가
# 프롬프트를 잠식하지 않도록 자른다.
_SCHEMA_MAX_CHARS = 4000


# ── LLM 구조화 출력 스키마 ───────────────────────────────────────


class CollectArguments(BaseModel):
    """도구 호출 인자 1회 산출.

    arguments를 dict가 아닌 JSON 문자열로 받는 이유: 자유형 dict는
    OpenAI strict structured output이 거부하고 provider마다 처리가 갈린다.
    문자열로 받아 이쪽에서 파싱하면 스키마가 도구와 무관하게 고정된다.
    """

    grounded: bool = Field(
        description=(
            "대화 맥락·이전 단계 결과에서 확인된 값만으로 인자를 채웠으면 true. "
            "추측하거나 지어낸 값이 하나라도 있으면 false"
        ),
    )
    arguments_json: str = Field(
        default="{}",
        description="도구 입력 스키마에 맞는 인자 객체를 JSON 문자열로",
    )
    missing: str = Field(
        default="",
        description="grounded=false일 때 어떤 정보가 없어서 채울 수 없었는지",
    )


ARGUMENT_SYSTEM_PROMPT = """당신은 도구 호출 인자를 작성하는 전문가입니다.
아래 도구의 입력 스키마에 맞는 인자 객체를 JSON 문자열 하나로 작성하세요.

규칙:
- 대화 맥락과 이전 단계 결과에서 '실제로 확인된 값'만 사용한다
- 값을 추측하거나 예시 주소(example.com 등)를 지어내지 않는다
- 확인된 값이 없어 필수 인자를 채울 수 없으면 grounded=false로 두고
  missing에 어떤 정보가 필요한지 적는다
- 도구는 한 번만 호출되므로 가장 적절한 인자 하나를 고른다
"""

COMPRESS_SYSTEM_PROMPT = """수집된 원문을 질문에 답하는 데 필요한 사실만 남겨 압축하세요.

규칙:
- 원문에 있는 수치·날짜·고유명사는 그대로 보존한다
- 원문에 없는 내용을 추가하거나 해석·분석을 덧붙이지 않는다
- 질문과 무관한 내비게이션·광고·반복 문구는 제거한다
"""


# ── 순수 헬퍼 ────────────────────────────────────────────────────


def _message_text(msg) -> str:
    if isinstance(msg, dict):
        return str(msg.get("content", ""))
    return str(getattr(msg, "content", ""))


def _message_role(msg) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role", ""))
    return str(getattr(msg, "type", ""))


def _collect_context(messages: list) -> str:
    """최근 대화 맥락 직렬화 — 워커 산출물도 포함한다.

    search 노드와 달리 이전 워커의 수집·검색 결과가 이번 호출 대상(URL 등)의
    출처인 경우가 많다(검색 → 상세 수집 체인). 따라서 제외하지 않는다.
    """
    recent = messages[-_CONTEXT_MAX_MESSAGES:]
    return "\n".join(
        f"{_message_role(m)}: {_message_text(m)[:_CONTEXT_MSG_SLICE]}" for m in recent
    )


def _resolve_input_schema(tool) -> dict:
    """도구의 실제 입력 스키마를 얻는다. 없으면 빈 dict.

    MCP 어댑터는 args_schema가 제네릭 래퍼라 쓸 수 없고, 서버가 준
    inputSchema를 별도 필드(mcp_input_schema)로 보존한다.
    """
    schema = getattr(tool, "mcp_input_schema", None)
    if isinstance(schema, dict) and schema:
        return schema
    args_schema = getattr(tool, "args_schema", None)
    model_json_schema = getattr(args_schema, "model_json_schema", None)
    if callable(model_json_schema):
        try:
            return model_json_schema() or {}
        except Exception:
            return {}
    return {}


def _is_mcp_adapter(tool) -> bool:
    """MCP 어댑터 판별 — 호출 페이로드를 arguments로 감싸야 하는 대상."""
    return bool(getattr(tool, "mcp_tool_name", None))


def _build_payload(tool, arguments: dict) -> dict:
    """MCPToolAdapter는 {"arguments": {...}} 형태를 받는다 (args_schema 계약)."""
    return {"arguments": arguments} if _is_mcp_adapter(tool) else arguments


def _parse_arguments(raw: object) -> dict | None:
    """구조화 출력의 arguments_json을 dict로 파싱. 실패 시 None."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _shortage_message(reason: str) -> str:
    """§6.1: 도구를 부르지 못한 이유를 하류가 읽을 수 있는 본문으로."""
    return (
        "수집을 수행하지 못했습니다.\n"
        f"사유: {reason}\n"
        "대화에서 수집 대상이 확인되지 않았습니다. "
        "추측한 값으로는 도구를 호출하지 않았습니다."
    )


# ── LLM 단계 ─────────────────────────────────────────────────────


class _ArgumentPlan:
    """인자 생성 결과. blocked/부재 사유를 함께 실어 나른다."""

    __slots__ = ("arguments", "reason", "llm_chars")

    def __init__(
        self, arguments: dict | None, reason: str = "", llm_chars: int = 0
    ) -> None:
        self.arguments = arguments
        self.reason = reason
        self.llm_chars = llm_chars

    @property
    def ok(self) -> bool:
        return self.arguments is not None


async def _build_arguments(
    llm, tool, question: str, context: str, logger: LoggerInterface,
    user_context: str = "",
) -> _ArgumentPlan:
    """도구 입력 스키마 기반 인자 1회 산출 (§6.1 #1·#2·#4 분기 포함)."""
    schema = _resolve_input_schema(tool)
    if not schema:
        # #4: 스키마를 모르면 키 이름을 추측하게 된다 — 호출하지 않는다.
        logger.warning(
            "collect_node input schema missing",
            tool=getattr(tool, "name", ""),
        )
        return _ArgumentPlan(None, "도구의 입력 스키마를 확인할 수 없습니다")

    schema_text = json.dumps(schema, ensure_ascii=False)[:_SCHEMA_MAX_CHARS]
    user_content = (
        f"[도구]\n{getattr(tool, 'name', '')}: {getattr(tool, 'description', '')}\n\n"
        f"[입력 스키마]\n{schema_text}\n\n"
        f"[대화 맥락]\n{context}\n\n[질문]\n{question}"
    )
    try:
        out = await llm.with_structured_output(CollectArguments).ainvoke([
            {"role": "system", "content": user_context + ARGUMENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ])
    except Exception as e:
        # #1: 그래프를 멈추지 않는다 — 근거 부족 경로로 낙하.
        logger.warning("collect_node argument build failed", error=str(e))
        return _ArgumentPlan(None, "인자 생성에 실패했습니다")

    llm_chars = len(getattr(out, "arguments_json", "") or "") + len(
        getattr(out, "missing", "") or ""
    )
    if not getattr(out, "grounded", False):
        # #2: 대상이 맥락에 없다 — 지어내지 않고 사유를 남긴다.
        return _ArgumentPlan(
            None, out.missing or "수집 대상을 대화에서 확인하지 못했습니다", llm_chars,
        )

    arguments = _parse_arguments(getattr(out, "arguments_json", "{}"))
    if arguments is None:
        logger.warning("collect_node argument parse failed")
        return _ArgumentPlan(None, "생성된 인자를 해석할 수 없습니다", llm_chars)
    return _ArgumentPlan(arguments, "", llm_chars)


async def _invoke_once(tool, arguments: dict, logger: LoggerInterface) -> tuple[bool, str]:
    """도구를 정확히 1회 호출한다. 예외는 실패 문자열로 (§6.1 #5)."""
    try:
        result = await tool.ainvoke(_build_payload(tool, arguments))
    except Exception as e:
        logger.error("collect_node tool failed", exception=e)
        return False, f"수집 실패: {e}"
    return True, result if isinstance(result, str) else str(result)


async def _maybe_compress(
    llm, policy: CollectPipelinePolicy, question: str, result: str,
    logger: LoggerInterface, user_context: str = "",
) -> tuple[str, int, bool]:
    """FR-09: 임계치 초과 시에만 1회 압축. 실패 시 원본 유지 (§6.1 #6)."""
    if not policy.needs_compression(result):
        return result, 0, False
    user_content = f"[질문]\n{question}\n\n[수집 원문]\n{result}"
    try:
        out = await llm.ainvoke([
            {"role": "system", "content": user_context + COMPRESS_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ])
        compressed = str(getattr(out, "content", "")).strip()
        if compressed:
            return compressed, len(compressed), True
        logger.warning("collect_node compress returned empty, keeping original")
    except Exception as e:
        logger.warning("collect_node compress failed, keeping original", error=str(e))
    return result, 0, False


class _BodyOutcome:
    """분기 판정 결과 — 본문과 관측 필드를 함께 나른다."""

    __slots__ = ("body", "invoked", "compressed", "blocked_value", "llm_chars")

    def __init__(
        self, body: str, invoked: bool, compressed: bool,
        blocked_value: str | None = None, llm_chars: int = 0,
    ) -> None:
        self.body = body
        self.invoked = invoked
        self.compressed = compressed
        self.blocked_value = blocked_value
        self.llm_chars = llm_chars


async def _resolve_body(
    plan: _ArgumentPlan, tool, llm, policy: CollectPipelinePolicy,
    question: str, logger: LoggerInterface, context_block: str = "",
) -> _BodyOutcome:
    """인자 상태에 따라 4갈래 중 하나로 본문을 만든다.

    Design Ref: Analysis Gap-02 — 노드 본문에 인라인이던 분기 결정을 분리했다.
    Design §10.4가 지시한 "단계별 헬퍼로 분해"의 마지막 조각이다.

    갈래: 근거 부족 / 인자 차단 / 정상 수집 / 도구 실패.
    어느 갈래도 예외를 올리지 않는다 (§6.1 계약).
    """
    if not plan.ok:
        return _BodyOutcome(_shortage_message(plan.reason), False, False)

    blocked = ToolArgumentPolicy.find_placeholder(plan.arguments)
    if blocked is not None:
        # §6.1 #3: 지어낸 예시 주소는 서버에 도달하기 전에 막는다. 어댑터에도
        # 같은 가드가 있지만(worker-context-injection §6.1) 여기서 막으면
        # 왕복 1회와 오해를 부르는 ToolMessage를 아낀다.
        return _BodyOutcome(
            ToolArgumentPolicy.build_blocked_message(blocked),
            False, False, blocked_value=blocked,
        )

    ok, text = await _invoke_once(tool, plan.arguments, logger)
    if not ok:
        return _BodyOutcome(text, True, False)

    text, chars, compressed = await _maybe_compress(
        llm, policy, question, text, logger, user_context=context_block,
    )
    return _BodyOutcome(text, True, compressed, llm_chars=chars)


# ── 노드 팩토리 ──────────────────────────────────────────────────


def create_collect_node(
    worker_id: str,
    tool,
    pipeline_llm,
    policy: CollectPipelinePolicy,
    logger: LoggerInterface,
    user_context_block: str = "",
    datetime_block: str = "",
    worker_context_block: str = "",
):
    """단일샷 collect 노드 생성 — 도구를 정확히 1회 호출한다 (FR-05).

    시그니처·반환 계약은 create_search_pipeline_node와 동일하다 (AD-1).
    블록 순서도 동일: 날짜 → 사용자 → 워커 (runtime-datetime-context §D4).
    인자를 실제로 작성하는 LLM이 날짜·사용자·에이전트 맥락을 모두 알아야
    근거 없는 인자를 만들지 않는다 (worker-context-injection §4.1).
    """
    context_block = datetime_block + user_context_block + worker_context_block

    async def collect_node(state: SupervisorState) -> dict:
        messages = state["messages"]
        question = latest_user_question(messages) or _message_text(messages[-1])

        plan = await _build_arguments(
            pipeline_llm, tool, question, _collect_context(messages), logger,
            user_context=context_block,
        )
        outcome = await _resolve_body(
            plan, tool, pipeline_llm, policy, question, logger, context_block,
        )

        logger.info(
            "collect_node executing",
            worker_id=worker_id,
            grounded=plan.ok,
            blocked=outcome.blocked_value is not None,
            invoked=outcome.invoked,
            compressed=outcome.compressed,
            length=len(outcome.body),
        )
        if outcome.blocked_value is not None:
            logger.warning(
                "collect_node argument blocked",
                worker_id=worker_id, blocked_value=outcome.blocked_value,
            )

        # FR-08: 어떤 분기에서도 근거 메시지 규약을 따른다 — 하류
        # analysis / final_answer / quality_gate가 수정 없이 소비한다.
        result_msg = AIMessage(
            content=format_search_result(worker_id, outcome.body), name=worker_id,
        )
        summary = (
            f"grounded={plan.ok} blocked={outcome.blocked_value is not None} "
            f"invoked={outcome.invoked} compressed={outcome.compressed} "
            f"len={len(outcome.body)}"
        )[:_SUMMARY_MAX_CHARS]
        llm_chars = plan.llm_chars + outcome.llm_chars
        return {
            "messages": [result_msg],
            "last_worker_id": worker_id,
            "token_usage": state["token_usage"] + (len(outcome.body) + llm_chars) // 4,
            STEP_OUTPUT_SUMMARY_KEY: summary,
        }

    return collect_node
