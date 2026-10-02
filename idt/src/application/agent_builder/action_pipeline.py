"""action 노드: 초안 작성 → 인자 조립 → 게이트 판정 → 도구 1회 호출.

Design Ref: action-category-compose-node §2.1 / §6.1 / D-02·D-04·D-06·D-08

collect 노드의 거울상이다(collect = 도구 1회 호출 → LLM 정리, action = LLM
작성 1회 → 도구 1회 호출). 시그니처·반환 계약은 create_collect_node와 동형(AD-1).

왜 react(create_agent)가 아닌가:
  react 워커는 "어떤 도구를 부를지"와 "본문 작성"을 한 LLM 호출에서 하고 본문이
  tool_call JSON 인자 안에 묻힌다. 승인 게이트는 그 인자에서 키를 추측해 초안을
  꺼내고, final_answer는 그걸 다시 쓴다. 이 노드는 초안을 먼저 만들어 워커
  산출(초안 규약)로 남기고, 발송 인자의 본문 키는 그 초안으로 덮어쓴다 —
  승인 화면·발송 본문·최종 답변이 같은 문자열이 된다.

compose(_compose_draft)와 dispatch(_dispatch_once)는 분리된 함수다(Plan FR-13).
후속 사이클의 "초안 전용(dispatch 없음)" 변형이 compose를 재사용한다.

어느 분기도 예외를 올리지 않는다(§6.1 계약). 게이트 대상인데 신호를 만들지
못하면 도구를 호출하지 않는다(fail-closed, §7).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from src.application.agent_builder.collect_pipeline import (
    CollectArguments,
    build_payload,
    collect_recent_context,
    parse_arguments_json,
    resolve_input_schema,
)
from src.application.agent_builder.message_normalization import ensure_user_tail
from src.application.agent_builder.search_pipeline import (
    format_draft_output,
    is_worker_output,
    latest_user_question,
)
from src.application.agent_builder.supervisor_state import SupervisorState
from src.application.agent_run.step_tracking import STEP_OUTPUT_SUMMARY_KEY
from src.application.hallucination.grounded_generation import GroundedGenerator
from src.domain.agent_builder.policies import ActionArgumentPolicy, ToolErrorPolicy
from src.domain.agent_builder.rag_tool_config import clamp_llm_name
from src.domain.approval.policies import ApprovalSignalPolicy
from src.domain.hallucination.grounding import INTERNAL_LLM_TAG
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy

# dispatch 결과를 워커 산출에 실을 때의 상한(자) — 재개 주입·final_answer 프롬프트 비대 방지.
_OUTCOME_MAX_CHARS = 4000
# state.last_worker_error 요약 상한 (collect·ToolErrorPolicy와 동일).
_WORKER_ERROR_MAX_CHARS = 200
_SUMMARY_MAX_CHARS = 512
# 인자 생성 프롬프트에 싣는 입력 스키마 최대 길이(자).
_SCHEMA_MAX_CHARS = 4000

PENDING_OUTCOME = "승인 대기로 등록되었습니다. 승인 후 발송됩니다."

COMPOSE_SYSTEM_PROMPT = """당신은 사용자를 대신해 외부로 나갈 글(메일·메시지·회신 등)의 초안을 작성합니다.

규칙:
- 아래 [근거]와 대화 맥락에서 확인된 사실만 사용하고, 없는 내용은 지어내지 않는다
- 출력은 초안 본문만 쓴다. 제목·수신자·인사말 이외의 설명, 머리말, 코드블록을 붙이지 않는다
- 에이전트 지침과 워커 설명이 정한 어조·형식을 따른다
"""

ACTION_ARGUMENT_SYSTEM_PROMPT = """당신은 도구 호출 인자를 작성하는 전문가입니다.
아래 도구의 입력 스키마에 맞는 인자 객체를 JSON 문자열 하나로 작성하세요.

규칙:
- 본문(초안)은 이미 작성되어 별도로 주입되므로 본문 필드는 비워 두거나 생략한다
- 수신자·제목 등 나머지 필드는 대화 맥락에서 '실제로 확인된 값'만 사용한다
- 값을 추측하거나 예시 주소(example.com 등)를 지어내지 않는다
- 확인된 값이 없어 필수 인자를 채울 수 없으면 grounded=false로 두고
  missing에 어떤 정보가 필요한지 적는다
- 도구는 한 번만 호출되므로 가장 적절한 인자 하나를 고른다
"""


# ── 순수 헬퍼 ────────────────────────────────────────────────────


def _is_tool_message(msg) -> bool:
    if isinstance(msg, dict):
        return msg.get("role") == "tool"
    return getattr(msg, "type", "") == "tool"


def _evidence_block(messages: list) -> str:
    """선행 워커 산출(검색·수집·분석)을 근거 블록으로 직렬화한다."""
    parts = [
        f"[{getattr(m, 'name', '')}]\n{getattr(m, 'content', '')}"
        for m in messages if is_worker_output(m)
    ]
    if not parts:
        return ""
    return "\n\n[근거]\n" + "\n\n---\n\n".join(parts)


def _conversation_messages(messages: list) -> list:
    """워커 산출·tool 메시지를 뺀 대화 본체 (final_answer와 같은 기준)."""
    return [m for m in messages if not is_worker_output(m) and not _is_tool_message(m)]


def _text_of(response) -> str:
    content = getattr(response, "content", response)
    return content if isinstance(content, str) else str(content)


@dataclass
class _ActionOutcome:
    """노드 한 번의 결과. 분기마다 채우는 필드가 다르다."""

    draft: str = ""
    outcome: str = ""
    error: str = ""
    invoked: bool = False
    ok: bool = False
    arg_keys: list[str] = field(default_factory=list)
    approval_pending: dict | None = None
    llm_chars: int = 0


# ── compose 단계 ─────────────────────────────────────────────────


async def _compose_draft(
    llm, messages: list, context_block: str, logger: LoggerInterface,
    *, feedback: str = "", internal: bool = False,
) -> tuple[str, str]:
    """에이전트 모델로 초안 1회 작성 → (draft, error). error가 비면 성공.

    draft-grounding-check §5.2: feedback(재작성 사유)은 system 끝에 덧붙이고,
    internal 이면 내부 태그로 채팅 스트림에서 뺀다. 둘 다 기본값이면 기존과 동일.
    """
    system = context_block + COMPOSE_SYSTEM_PROMPT + _evidence_block(messages)
    if feedback:
        system += "\n\n" + feedback
    llm_messages = [
        {"role": "system", "content": system},
        *ensure_user_tail(
            _conversation_messages(messages),
            instruction="위 대화와 근거를 바탕으로 초안 본문을 작성하세요.",
        ),
    ]
    try:
        if internal:
            response = await llm.ainvoke(llm_messages, config={"tags": [INTERNAL_LLM_TAG]})
        else:
            response = await llm.ainvoke(llm_messages)
    except Exception as e:
        logger.warning("action_node compose failed", error=str(e))
        return "", f"초안 작성 실패: {e}"
    draft = _text_of(response)
    if not draft.strip():
        return "", "초안 작성 실패: 초안이 비었습니다"
    return draft, ""


class _ComposeFailed(Exception):
    """근거 루프 첫 작성 실패 — 루프를 멈추고 기존 작성 실패 경로로 보낸다."""


def _message_text(m) -> str:
    content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
    return content if isinstance(content, str) else str(content)


def _grounding_sources(messages: list, context_block: str) -> str:
    """판정 근거 코퍼스 — 지침 → 최신 워커 산출 → 대화 순 (D-10: 상한 절단 시 앞쪽 우선)."""
    evidence = [
        f"[{getattr(m, 'name', '')}]\n{_message_text(m)}"
        for m in reversed(messages) if is_worker_output(m)
    ]
    conversation = [_message_text(m) for m in _conversation_messages(messages)]
    return "\n\n".join(p for p in (context_block, *evidence, *conversation) if p.strip())


async def _compose_grounded(
    llm, messages: list, context_block: str, logger: LoggerInterface,
    grounded: GroundedGenerator, max_retries: int, request_id: str,
) -> tuple[str, str]:
    """근거 재작성 루프를 거친 초안 → (draft, error). Design Ref: §5.2."""

    async def generate(feedback: str) -> str:
        draft, error = await _compose_draft(
            llm, messages, context_block, logger, feedback=feedback, internal=True,
        )
        if error:
            raise _ComposeFailed(error)
        return draft

    try:
        result = await grounded.run(
            generate=generate, question=latest_user_question(messages),
            sources=_grounding_sources(messages, context_block),
            max_retries=max_retries, target="draft", request_id=request_id,
        )
    except _ComposeFailed as e:
        return "", str(e)
    if not result.text.strip():
        # D-07: 근거 없는 문장을 빼고 나니 남은 초안이 없다.
        return "", "초안 작성 실패: 근거로 확인되는 내용이 없어 초안을 만들지 못했습니다"
    return result.text, ""


# ── 인자 조립 단계 ───────────────────────────────────────────────


_PARSE_FAILED = "발송 인자 생성 실패: 생성된 인자를 해석할 수 없습니다"
# approval-gate-run-termination Analysis G1: 파싱 실패 시 재시도 횟수 (총 시도 = 1 + 이 값)
_ARGUMENT_PARSE_RETRIES = 1


def _schema_without(schema: dict, key: str) -> dict:
    """본문 키를 뺀 스키마 사본 — 보조 LLM 이 본문을 다시 쓰지 않게 한다 (G1).

    실측: "본문은 비워라" 지시만으로는 수천 자 본문을 arguments_json 에 옮겨 적다
    파싱이 깨졌다. 스키마에서 아예 없애고, 본문은 병합 단계가 초안으로 채운다.
    """
    props = {k: v for k, v in (schema.get("properties") or {}).items() if k != key}
    stripped = {**schema, "properties": props}
    if "required" in schema:
        stripped["required"] = [r for r in schema.get("required") or [] if r != key]
    return stripped


def _argument_user_content(
    tool, schema: dict, draft: str, messages: list, draft_key: str,
) -> str:
    schema_text = json.dumps(schema, ensure_ascii=False)[:_SCHEMA_MAX_CHARS]
    question = latest_user_question(messages)
    return (
        f"[도구]\n{getattr(tool, 'name', '')}: {getattr(tool, 'description', '')}\n\n"
        f"[입력 스키마]\n{schema_text}\n\n"
        f"[본문] '{draft_key}' 필드는 이미 작성된 초안({len(draft)}자)이 자동으로 채워진다 — "
        "인자에 넣지 말 것\n\n"
        f"[대화 맥락]\n{collect_recent_context(messages)}\n\n[요청]\n{question}"
    )


async def _request_arguments(pipeline_llm, context_block: str, user_content: str):
    return await pipeline_llm.with_structured_output(CollectArguments).ainvoke([
        {"role": "system", "content": context_block + ACTION_ARGUMENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ])


def _interpret_arguments(out) -> tuple[dict | None, str, int]:
    """구조화 출력 → (arguments, error, llm_chars). 파싱 실패는 _PARSE_FAILED."""
    raw = getattr(out, "arguments_json", "") or ""
    chars = len(raw) + len(getattr(out, "missing", "") or "")
    if not getattr(out, "grounded", False):
        missing = getattr(out, "missing", "") or "필수 인자를 대화에서 확인하지 못했습니다"
        return None, f"발송 대상을 확인하지 못했습니다: {missing}", chars
    arguments = parse_arguments_json(raw or "{}")
    if arguments is None:
        return None, _PARSE_FAILED, chars
    return arguments, "", chars


async def _assemble_arguments(
    pipeline_llm, tool, draft: str, messages: list, context_block: str,
    logger: LoggerInterface, draft_key: str = "",
) -> tuple[dict | None, str, int]:
    """보조 LLM이 초안 이외 필드를 채운다 → (arguments, error, llm_chars)."""
    schema = resolve_input_schema(tool)
    if not schema:
        return None, "발송 인자 생성 실패: 도구의 입력 스키마를 확인할 수 없습니다", 0
    user_content = _argument_user_content(
        tool, _schema_without(schema, draft_key), draft, messages, draft_key,
    )
    total = 0
    for attempt in range(1 + _ARGUMENT_PARSE_RETRIES):
        try:
            out = await _request_arguments(pipeline_llm, context_block, user_content)
        except Exception as e:
            logger.warning("action_node argument build failed", error=str(e))
            return None, f"발송 인자 생성 실패: {e}", total
        arguments, error, chars = _interpret_arguments(out)
        total += chars
        if error != _PARSE_FAILED:
            return arguments, error, total
        # G1: 파싱 실패만 재시도 — grounded=false 는 정보 부족이라 다시 물어도 같다.
        logger.warning("action_node argument parse retry", attempt=attempt + 1)
    return None, _PARSE_FAILED, total


# ── 게이트 / dispatch 단계 ───────────────────────────────────────


def _build_signal(tool_id: str, worker_id: str, arguments: dict, draft: str) -> dict | None:
    """ApprovalSignalPolicy로 마커를 만들고 되읽어 dict를 채운다 (§6.2).

    render→extract 왕복은 react 래퍼(_extract_approval_pending)와 형식이 갈라지는
    것을 막는 가장 싼 방법이다. 실패하면 None — 호출자가 fail-closed 처리.
    """
    try:
        content = ApprovalSignalPolicy.render(
            tool_id=tool_id, tool_args=arguments, draft=draft,
            tool_call_id=uuid.uuid4().hex,
        )
        signal = ApprovalSignalPolicy.extract([SimpleNamespace(content=content)])
    except Exception:
        return None
    if signal is None:
        return None
    return {
        "tool_id": signal.tool_id,
        "tool_args": signal.tool_args,
        "draft": signal.draft,
        "tool_call_id": signal.tool_call_id,
        "worker_id": worker_id,
    }


async def _dispatch_once(tool, arguments: dict, logger: LoggerInterface) -> tuple[bool, str]:
    """도구를 정확히 1회 호출한다. 재시도 없음 — 비가역 작업의 재시도는 이중 집행.

    Analysis GAP-I2: MCP 어댑터는 도구 오류(isError)를 예외가 아니라
    'Error executing tool…' 문자열로 돌려준다 — ToolErrorPolicy 접두 판정으로
    실패로 기록해야 final_answer가 실패를 성공으로 보고하지 않는다.
    GAP-I3: 실패 문구도 상한 절단 — 예외 전문이 프롬프트로 전파되지 않는다.
    """
    try:
        result = await tool.ainvoke(build_payload(tool, arguments))
    except Exception as e:
        logger.error("action_node dispatch failed", exception=e)
        return False, f"집행 실패: {e}"[:_OUTCOME_MAX_CHARS]
    text = (result if isinstance(result, str) else str(result))[:_OUTCOME_MAX_CHARS]
    if text.lstrip().startswith(ToolErrorPolicy.ERROR_PREFIXES):
        logger.warning("action_node dispatch returned tool error", length=len(text))
        return False, f"집행 실패: {text}"[:_OUTCOME_MAX_CHARS]
    return True, text


async def _resolve_after_draft(
    out: _ActionOutcome, *, tool, tool_id: str, worker_id: str, draft_key: str,
    gated: bool, pipeline_llm, messages: list, context_block: str, logger: LoggerInterface,
) -> _ActionOutcome:
    """초안 확보 이후의 분기: 인자 조립 → 차단 검사 → 게이트 또는 dispatch."""
    arguments, error, chars = await _assemble_arguments(
        pipeline_llm, tool, out.draft, messages, context_block, logger,
        draft_key=draft_key,
    )
    out.llm_chars += chars
    if arguments is None:
        out.outcome, out.error = error, error
        return out
    merged = ActionArgumentPolicy.merge(arguments, draft_key, out.draft)  # Plan SC: SC-2/SC-3 — 초안이 이긴다
    out.arg_keys = ActionArgumentPolicy.summarize_keys(merged)
    blocked = ToolArgumentPolicy.find_placeholder(merged)
    if blocked is not None:
        out.outcome = ToolArgumentPolicy.build_blocked_message(blocked)
        out.error = out.outcome
        return out
    if gated:
        out.approval_pending = _build_signal(tool_id, worker_id, merged, out.draft)
        if out.approval_pending is None:
            out.outcome = "승인 신호 생성 실패 — 실행하지 않았습니다"
            out.error = out.outcome
            return out
        out.outcome, out.ok = PENDING_OUTCOME, True
        return out
    out.invoked = True
    out.ok, out.outcome = await _dispatch_once(tool, merged, logger)
    if not out.ok:
        out.error = out.outcome
    return out


# ── 노드 팩토리 ──────────────────────────────────────────────────


def create_action_node(
    worker_id: str,
    tool,
    tool_id: str,
    llm,
    pipeline_llm,
    draft_key: str,
    gated: bool,
    logger: LoggerInterface,
    user_context_block: str = "",
    datetime_block: str = "",
    worker_context_block: str = "",
    grounded: GroundedGenerator | None = None,
    grounding_max_retries: int = 2,
    request_id: str = "",
):
    """action 노드 생성 — 초안 1회 작성 후 도구를 정확히 1회 호출(또는 승인 대기).

    grounded 가 활성이면 초안은 근거 재작성 루프를 거친다(draft-grounding-check
    §5.2). 비활성·미주입이면 기존 1회 작성과 호출·프롬프트가 같다.

    tool_id는 카탈로그 형식(`mcp:<srv>:<tool>`)이다 — 런타임 합성명(tool.name)이
    아니다(위키 mcp-runtime-tool-shape). draft_key는 컴파일러가
    ActionArgumentPolicy로 확정하고, gated는 미들웨어 부착 판정과 같은 함수로
    계산한다(D-03). 블록 순서는 collect와 동일: 날짜 → 사용자 → 워커.
    """
    context_block = datetime_block + user_context_block + worker_context_block

    async def action_node(state: SupervisorState) -> dict:
        messages = state["messages"]
        out = _ActionOutcome()
        if grounded is not None and grounded.active:
            out.draft, out.error = await _compose_grounded(
                llm, messages, context_block, logger,
                grounded, grounding_max_retries, request_id,
            )
        else:
            out.draft, out.error = await _compose_draft(llm, messages, context_block, logger)
        out.llm_chars += len(out.draft)
        if out.error:
            out.outcome = out.error
        else:
            out = await _resolve_after_draft(
                out, tool=tool, tool_id=tool_id, worker_id=worker_id,
                draft_key=draft_key, gated=gated, pipeline_llm=pipeline_llm,
                messages=messages, context_block=context_block, logger=logger,
            )
        return _emit(state, worker_id, out, gated, logger)

    return action_node


def _emit(state: SupervisorState, worker_id: str, out: _ActionOutcome, gated: bool, logger) -> dict:
    """반환 dict 조립 — collect와 동형 + (게이트 시) approval_pending."""
    summary = (
        f"draft_len={len(out.draft)} arg_keys={out.arg_keys} gated={gated} "
        f"invoked={out.invoked} ok={out.ok}"
    )[:_SUMMARY_MAX_CHARS]
    logger.info(
        "action_node executing", worker_id=worker_id, draft_len=len(out.draft),
        arg_keys=out.arg_keys, gated=gated, invoked=out.invoked, ok=out.ok,
    )
    body = format_draft_output(worker_id, out.draft, out.outcome)
    result: dict = {
        "messages": [AIMessage(content=body, name=clamp_llm_name(worker_id))],
        "last_worker_id": worker_id,
        "token_usage": state["token_usage"] + (out.llm_chars + len(out.outcome)) // 4,
        "last_worker_error": out.error[:_WORKER_ERROR_MAX_CHARS],
        STEP_OUTPUT_SUMMARY_KEY: summary,
    }
    if out.approval_pending is not None:
        result["approval_pending"] = out.approval_pending
    return result
