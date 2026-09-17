"""search 노드 파이프라인: rewrite → search → validate(루프) → compress.

search-node-query-pipeline Design §2-2.
- 검색 시도 총 3회(최초 1 + 재시도 2), 마지막 시도 후 validate 생략 (D1)
- 도구 예외 시 validate 생략 즉시 재시도 (D4)
- 모든 LLM 단계는 graceful fallback — 그래프 비중단 (§3 실패 분기 매트릭스)

이 모듈은 search 워커 메시지 규약([worker_id 검색결과])의 단일 출처다 (D2).
workflow_compiler / final_answer / analysis 노드가 여기의 predicate를 import한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from src.application.agent_builder.supervisor_state import SupervisorState
from src.application.agent_run.step_tracking import STEP_OUTPUT_SUMMARY_KEY
from src.domain.agent_builder.rag_tool_config import clamp_llm_name
from src.domain.agent_builder.policies import SearchPipelinePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface

# ── 메시지 규약 (D2: 단일 출처) ──────────────────────────────────

SEARCH_RESULT_MARKER = "검색결과"

# supervisor_nodes.quality_gate가 재시도 피드백 메시지에 사용하는 prefix.
# latest_user_question이 피드백을 실제 질문으로 오인하지 않도록 식별에 사용 (D5).
QUALITY_FEEDBACK_PREFIX = "[품질검증 실패]"

# validate 판정에 사용할 검색 결과 head 길이(자) — 프롬프트 비대 방지.
_VALIDATE_RESULT_HEAD = 3000
# rewrite 맥락에 포함할 최근 대화 메시지 수 / 메시지당 길이 (D5).
_CONTEXT_MAX_MESSAGES = 6
_CONTEXT_MSG_SLICE = 500
_SUMMARY_MAX_CHARS = 512


def format_search_result(worker_id: str, body: str) -> str:
    """search 워커 산출 메시지 본문 규약 — is_search_result 식별과 쌍."""
    return f"[{worker_id} {SEARCH_RESULT_MARKER}]\n{body}"


def is_search_result(msg) -> bool:
    """search 워커가 추가한 검색결과 AIMessage 식별.

    search 노드는 AIMessage(name=<worker_id>, content="[... 검색결과]\\n...") 형태로 추가.
    final_answer_node / analysis_node가 컨텍스트 블록을 분류할 때 공용 사용.
    """
    if isinstance(msg, dict):
        return False
    name = getattr(msg, "name", None)
    content = getattr(msg, "content", "")
    return bool(name) and SEARCH_RESULT_MARKER in content


def is_worker_output(msg) -> bool:
    """워커 노드가 생성한 AIMessage 식별.

    search/analysis/sub_agent 노드는 모두 AIMessage(name=<worker_id>) 규약을 따른다.
    """
    if isinstance(msg, dict):
        return False
    return bool(getattr(msg, "name", None)) and getattr(msg, "type", "") == "ai"


def _message_text(msg) -> str:
    if isinstance(msg, dict):
        return str(msg.get("content", ""))
    return str(getattr(msg, "content", ""))


def _message_role(msg) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role", ""))
    return str(getattr(msg, "type", ""))


def latest_user_question(messages: list) -> str:
    """가장 최근 user/human 메시지 content 추출 (없으면 빈 문자열).

    quality_gate 재시도 피드백(role=user로 주입됨)은 실제 질문이 아니므로 건너뛴다 (D5).
    """
    for msg in reversed(messages):
        if _message_role(msg) not in ("user", "human"):
            continue
        content = _message_text(msg)
        if content.startswith(QUALITY_FEEDBACK_PREFIX):
            continue
        return content
    return ""


# ── LLM 구조화 출력 스키마 ───────────────────────────────────────


class RewrittenQuery(BaseModel):
    query: str = Field(description="검색 엔진에 보낼 최적화 쿼리 (핵심 키워드 중심 한 문장)")
    reasoning: str = Field(default="", description="재작성 근거")


class SearchResultVerdict(BaseModel):
    relevant: bool = Field(
        description="검색 결과가 질문과 관련 있으면 true. 명백히 무관할 때만 false",
    )
    reason: str = Field(default="")
    improved_query: str = Field(
        default="", description="relevant=false일 때 다시 검색할 개선 쿼리",
    )


# ── 프롬프트 ─────────────────────────────────────────────────────

REWRITE_SYSTEM_PROMPT = """당신은 검색 쿼리 작성 전문가입니다.
사용자 질문과 대화 맥락에서 '검색해야 할 정보'만 추출해 검색 엔진에 최적화된 쿼리 하나를 작성하세요.

규칙:
- 그래프/차트/표 등 출력 형식 요구는 제거한다 (검색 대상이 아님)
- 핵심 주제·기간·지역·지표를 보존한다
- 대화 맥락의 지시어(그거, 아까 그 자료)는 실제 대상으로 치환한다
- 질문이 사용자 본인에 대한 것('나', '내', '본인')이고 [현재 사용자 정보]가
  주어졌다면, 1인칭 표현을 해당 사용자 이름으로 치환해 쿼리에 포함한다
- 일반 지식·정책·업무 절차 질문에는 사용자 이름을 넣지 않는다
- 한 문장, 명사구 중심으로 작성한다

예시:
질문: "대한민국 2025년 실업률 정보를 가지고 월별 %별 그래프를 그려줄 수 있니?"
쿼리: "대한민국 2025년 월별 실업률 통계"

예시 ([현재 사용자 정보] 이름: 배상규 가 주어진 경우):
질문: "나의 남은 휴가 개수와 월별 사용 현황 그래프로 보여줄 수 있겠니?"
쿼리: "배상규 남은 휴가 개수 월별 사용 현황"
"""

VALIDATE_SYSTEM_PROMPT = """검색 결과가 질문에 답하는 데 쓸 수 있는지 판정하세요.

규칙:
- 결과가 질문 주제와 명백히 무관하거나, 오류/빈 내용일 때만 relevant=false
- 부분적으로라도 유용하면 relevant=true (과도한 재검색 방지)
- relevant=false면 improved_query에 더 정확한 대안 쿼리를 제안하세요
"""

COMPRESS_SYSTEM_PROMPT = """검색 결과에서 질문에 답하는 데 필요한 정보만 추려 압축하세요.

규칙:
- 수치, 날짜, 단위, 출처(URL/기관명)는 반드시 보존한다
- 질문과 무관한 광고·내비게이션·중복 문장은 제거한다
- 원문에 없는 내용을 추가하거나 추측하지 않는다
- 목록/표 형태로 구조화해 작성한다
"""


# ── 파이프라인 단계 함수 (§3: 모두 graceful fallback) ────────────


def _collect_context(messages: list) -> str:
    """워커 산출물을 제외한 최근 대화 맥락 직렬화 (D5)."""
    conversation = [m for m in messages if not is_worker_output(m)]
    recent = conversation[-_CONTEXT_MAX_MESSAGES:]
    return "\n".join(
        f"{_message_role(m)}: {_message_text(m)[:_CONTEXT_MSG_SLICE]}" for m in recent
    )


async def _rewrite_query(
    llm, question: str, context: str, logger: LoggerInterface,
    user_context: str = "",
) -> tuple[str, int]:
    """검색 최적화 쿼리 생성. 실패/빈 결과 시 원본 질문 fallback.

    rag-auth-filter-fix D5: user_context(사용자 컨텍스트 블록)가 주어지면
    system prompt 앞에 prepend — 1인칭 질의를 사용자 이름으로 치환 가능하게.
    """
    user_content = f"[대화 맥락]\n{context}\n\n[질문]\n{question}"
    try:
        out = await llm.with_structured_output(RewrittenQuery).ainvoke([
            {"role": "system", "content": user_context + REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ])
        rewritten = (out.query or "").strip()
        if rewritten:
            return rewritten, len(out.query) + len(out.reasoning)
        logger.warning("search_pipeline rewrite returned empty query, using question")
    except Exception as e:
        logger.warning(
            "search_pipeline rewrite failed, using original question", error=str(e),
        )
    return question, 0


async def _validate_result(
    llm, question: str, query: str, result: str, logger: LoggerInterface,
    user_context: str = "",
) -> tuple[SearchResultVerdict, int]:
    """검색 결과 관련성 판정. 실패 시 통과 처리(relevant=True).

    rag-auth-filter-fix D5: '나의 질문 ↔ 사용자 이름이 담긴 결과'의 동일성을
    판정할 수 있도록 사용자 블록을 함께 주입 (오판 재검색 루프 방지).
    """
    user_content = (
        f"[질문]\n{question}\n\n[사용한 검색 쿼리]\n{query}\n\n"
        f"[검색 결과]\n{result[:_VALIDATE_RESULT_HEAD]}"
    )
    try:
        verdict = await llm.with_structured_output(SearchResultVerdict).ainvoke([
            {"role": "system", "content": user_context + VALIDATE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ])
        return verdict, len(verdict.reason) + len(verdict.improved_query)
    except Exception as e:
        logger.warning(
            "search_pipeline validate failed, passing result through", error=str(e),
        )
        return SearchResultVerdict(relevant=True), 0


async def _compress_result(
    llm, question: str, result: str, logger: LoggerInterface,
    user_context: str = "",
) -> tuple[str, int]:
    """검색 결과 압축. 실패/빈 응답 시 원문 유지."""
    user_content = f"[질문]\n{question}\n\n[검색 결과]\n{result}"
    try:
        out = await llm.ainvoke([
            {"role": "system", "content": user_context + COMPRESS_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ])
        compressed = str(getattr(out, "content", "")).strip()
        if compressed:
            return compressed, len(compressed)
        logger.warning("search_pipeline compress returned empty, keeping original")
    except Exception as e:
        logger.warning(
            "search_pipeline compress failed, keeping original", error=str(e),
        )
    return result, 0


async def _safe_search(tool, query: str, logger: LoggerInterface) -> tuple[bool, str]:
    """검색 도구 호출. 예외 시 (False, 실패 메시지) — 그래프 비중단 (FR-11)."""
    try:
        result = await tool.ainvoke({"query": query})
    except Exception as e:
        logger.error("search_node tool failed", exception=e)
        return False, f"검색 실패: {e}"
    return True, result if isinstance(result, str) else str(result)


@dataclass
class _SearchLoopResult:
    text: str
    attempts: int
    validated: bool
    ok: bool
    llm_chars: int
    query: str


async def _search_with_validation(
    tool, llm, policy: SearchPipelinePolicy,
    question: str, query: str, logger: LoggerInterface,
    user_context: str = "",
) -> _SearchLoopResult:
    """검색 + 검증 루프 (D1/D4). 시도 한도 소진 시 마지막 결과 채택."""
    attempt, llm_chars, validated = 0, 0, False
    ok, text = False, ""
    while True:
        attempt += 1
        ok, text = await _safe_search(tool, query, logger)
        if policy.is_last_attempt(attempt):
            logger.warning(
                "search_pipeline attempts exhausted, using last result",
                attempts=attempt, validated=False, ok=ok,
            )
            break
        if not ok:
            continue  # D4: 도구 예외 — validate 생략 즉시 재시도
        verdict, chars = await _validate_result(
            llm, question, query, text, logger, user_context=user_context,
        )
        llm_chars += chars
        if verdict.relevant:
            validated = True
            break
        logger.info(
            "search_pipeline result rejected, retrying",
            attempt=attempt, reason=verdict.reason[:200],
        )
        query = verdict.improved_query or query
    return _SearchLoopResult(text, attempt, validated, ok, llm_chars, query)


# ── 노드 팩토리 ──────────────────────────────────────────────────


def create_search_pipeline_node(
    worker_id: str,
    tool,
    pipeline_llm,
    policy: SearchPipelinePolicy,
    logger: LoggerInterface,
    user_context_block: str = "",
    datetime_block: str = "",
    worker_context_block: str = "",
):
    """rewrite → search → validate(루프) → compress 파이프라인 search 노드 생성.

    rag-auth-filter-fix D5: user_context_block(include_user_context 게이팅된
    사용자 컨텍스트)이 주어지면 3단계 LLM system prompt 모두에 prepend된다.
    runtime-datetime-context D4: datetime_block([현재 날짜])은 사용자 블록보다
    앞에 prepend — 검색어를 실제로 작성하는 rewrite LLM이 날짜를 알아야 한다 (FR-05a).
    worker-context-injection §4.1 (GAP-01): worker_context_block([에이전트 지침]·
    [당신의 역할])은 사용자 블록 뒤 — rewrite LLM이 어떤 에이전트의 어떤 작업으로
    검색어를 쓰는지 알아야 근거 없는 검색어를 만들지 않는다.
    """
    # Design Ref: runtime-datetime-context §D4 — 순서: 날짜 → 사용자 → 워커 → 본문
    context_block = datetime_block + user_context_block + worker_context_block

    async def search_node(state: SupervisorState) -> dict:
        messages = state["messages"]
        question = latest_user_question(messages) or _message_text(messages[-1])
        context = _collect_context(messages)

        query, llm_chars = await _rewrite_query(
            pipeline_llm, question, context, logger,
            user_context=context_block,
        )
        loop = await _search_with_validation(
            tool, pipeline_llm, policy, question, query, logger,
            user_context=context_block,
        )
        llm_chars += loop.llm_chars

        result_str, compressed = loop.text, False
        if loop.ok and policy.needs_compression(result_str):
            result_str, chars = await _compress_result(
                pipeline_llm, question, result_str, logger,
                user_context=context_block,
            )
            llm_chars += chars
            compressed = True

        logger.info(
            "search_node executing", worker_id=worker_id,
            query_length=len(loop.query), attempts=loop.attempts,
            validated=loop.validated, compressed=compressed,
        )

        result_msg = AIMessage(
            content=format_search_result(worker_id, result_str), name=clamp_llm_name(worker_id),
        )
        summary = (
            f"query='{loop.query}' attempts={loop.attempts} "
            f"validated={loop.validated} compressed={compressed} len={len(result_str)}"
        )[:_SUMMARY_MAX_CHARS]
        return {
            "messages": [result_msg],
            "last_worker_id": worker_id,
            "token_usage": state["token_usage"] + (len(result_str) + llm_chars) // 4,
            STEP_OUTPUT_SUMMARY_KEY: summary,
        }

    return search_node
