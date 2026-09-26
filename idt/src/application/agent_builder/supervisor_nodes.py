"""Supervisor 그래프 노드 함수: supervisor, quality_gate, routing."""
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from src.application.agent_builder.message_normalization import ensure_user_tail
from src.application.agent_builder.search_pipeline import (
    QUALITY_FEEDBACK_PREFIX,
    is_search_result,
    latest_user_question,
)
from src.application.agent_builder.supervisor_hooks import SupervisorHooks
from src.application.agent_builder.supervisor_state import SupervisorState
from src.application.agent_run.context import get_current_run_context
from src.domain.agent_builder.policies import QualityGatePolicy
from src.domain.conversation.analysis_snapshot_policy import AnalysisSnapshotPolicy
from src.domain.agent_builder.schemas import SupervisorConfig, WorkerDefinition
from src.domain.agent_run.value_objects import RunPurpose
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.visualization.policies import VisualizationRoutingPolicy


def _render_attachment_block(attachments: list[dict] | None) -> str:
    """첨부 목록 → supervisor decision용 인지 블록 (없으면 빈 문자열).

    임시경로 노출 방지: file_name이 있으면 표기, 없으면 타입만 표기.
    """
    if not attachments:
        return ""
    labels = []
    for a in attachments:
        kind = a.get("type", "파일")
        name = a.get("file_name")
        labels.append(f"{kind}({name})" if name else kind)
    joined = ", ".join(labels)
    return (
        f"\n\n[첨부된 데이터]\n사용자가 다음을 첨부했습니다: {joined}.\n"
        f"이 데이터를 분석할 수 있는 워커가 사용 가능 목록에 있으면, "
        f"권한이 없다고 거부하지 말고 반드시 그 워커로 라우팅하세요."
    )


def _current_turn_messages(messages: list) -> list:
    """마지막 사용자 메시지 이후의 메시지들 — 이번 턴 워커 산출물 판정용."""
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "type", "")
        if role in ("user", "human"):
            return messages[idx + 1:]
    return list(messages)


def _wiki_read_this_turn(messages: list, wiki_worker_id: str) -> bool:
    """이번 턴에 wiki 워커 산출물이 있는가 — 재주입분(이전 턴 스냅샷)은 제외."""
    if not wiki_worker_id:
        return False
    for msg in _current_turn_messages(messages):
        if getattr(msg, "name", None) != wiki_worker_id:
            continue
        if not AnalysisSnapshotPolicy.is_reinjected(getattr(msg, "content", "")):
            return True
    return False


def _render_worker_error_block(state, wiki_worker_id: str) -> str:
    """직전 수집 워커 실패 안내 블록 (wiki-guided-routing D4). 오류 없으면 ''.

    Design Ref: D4 — 실패 신호는 결정적(state.last_worker_error), 그 다음 행동
    (위키 재확인 → 없으면 되묻기)은 LLM 판단. URL·식별자 추측 재시도를 막는다.
    Plan SC: FR-05.
    """
    err = state.get("last_worker_error", "") or ""
    if not err:
        return ""
    last_worker = state.get("last_worker_id", "") or "직전 워커"
    lines = [
        "\n\n[직전 수집 실패]",
        f"직전 워커({last_worker})의 도구 호출이 실패했습니다: {err}",
    ]
    if wiki_worker_id and not _wiki_read_this_turn(state.get("messages", []), wiki_worker_id):
        lines.append(
            f"- 위키 목차에 관련 지침(대상 URL·절차)이 있는지 먼저 {wiki_worker_id}로 "
            f"확인하세요."
        )
    lines.append(
        "- 지침에도 대상이 없으면 URL·식별자를 추측해 재시도하지 말고 'FINISH'를 "
        "선택하고, answer에 어떤 사이트(URL)를 대상으로 할지 사용자에게 묻는 문장을 "
        "쓰세요."
    )
    lines.append("- 같은 인자로 같은 워커를 다시 부르지 마세요.")
    return "\n".join(lines)


def _render_empty_result_block(state) -> str:
    """수집 성공 + 유효 데이터 부재 안내 블록. 신호 없으면 ''.

    Design Ref: supervisor-early-finish-fix §4.3 (D-03). Plan SC: FR-05.

    그래프 계약 ②(목록 프레이밍 금지)에 따라 워커·도구 이름을 나열하지 않는다 —
    화이트리스트는 방어 지시를 이기고 과차단을 부른다. '남아 있다면'이라는
    조건부 서술로만 적어, 오탐일 때 LLM이 곧바로 FINISH를 재선택할 수 있게 한다.
    """
    reason = state.get("last_worker_empty", "") or ""
    if not reason:
        return ""
    return "\n".join([
        "\n\n[수집 결과 확인 필요]",
        f"직전 워커는 정상 실행됐지만 유효한 데이터가 확인되지 않았습니다: {reason}",
        "- 조작(검색 실행·조건 적용 등)이 선행돼야 데이터가 나타나는 페이지일 수 있습니다.",
        "- 아직 시도하지 않은 방법이 남아 있다면 FINISH 대신 그 방법을 먼저 시도하세요.",
        "- 이미 충분히 시도했다면 FINISH를 선택하고, 무엇이 확인되지 않았는지 answer에 밝히세요.",
    ])


# 능력 부정 블록에 싣는 사유 요약 절단 길이 — 블록 총 400자 상한 보장 (Gap-07).
_DENIAL_REASON_MAX_CHARS = 60

# Act-1 Gap-03: 되물음 재진입 리마인더 — 사유 종류별 1줄.
_CHALLENGE_REENTRY_HINTS = {
    "denial": "직전 워커 산출의 '불가' 선언은 그 워커의 도구 범위일 뿐입니다.",
    "empty": "직전 워커는 정상 실행됐지만 유효한 데이터가 확인되지 않았습니다.",
}


def _render_challenge_reentry_block(state: SupervisorState) -> str:
    """되물음 재결정용 리마인더. pending이 아니면 ''.

    Act-1 Gap-03 (실런 295d2915): 1회차 재판단은 옳았으나 FINISH answer는
    DQ1로 폐기되고 reasoning은 대화에 남지 않아, 블록 없는 2회차가 원래
    믿음으로 되돌아갔다. 신호 채널은 이미 리셋돼 있으므로 종류만 알린다 —
    pending은 재진입에서 False로만 가고 1회 상한은 그대로다.
    """
    if not state.get("finish_challenge_pending"):
        return ""
    hint = _CHALLENGE_REENTRY_HINTS.get(state.get("finish_challenge_kind", ""), "")
    return "\n".join([
        "\n\n[되물음 재결정]",
        "직전 결정(FINISH)은 아래 사유로 한 번 되돌려졌습니다. 이번이 재결정입니다.",
        f"- {hint}" if hint else "- 직전 워커 산출에 확인이 필요한 신호가 있었습니다.",
        "- 에이전트 능력 판단은 위 '사용 가능한 워커' 목록으로만 하세요. "
        "요청 기능을 가진 워커가 있으면 호출하고, 없으면 FINISH하되 무엇이 불가한지 밝히세요.",
    ])


def _render_capability_denial_block(state: SupervisorState) -> str:
    """워커의 '에이전트 능력 부정' 안내 블록. 신호 없으면 ''.

    Design Ref: worker-capability-denial-guard §4.3 (D-05). Plan SC: FR-06, FR-10.

    그래프 계약 ②(목록 프레이밍 금지)에 따라 워커·도구 이름을 나열하지 않는다 —
    "목록에 있으면"이라는 조건부 서술로만 쓴다. 판단은 LLM에 맡긴다(계약 ③).
    FR-10 전환 지점: '능동 조회' 모드로 바꾸려면 4번째 항목만 교체한다.
    """
    reason = state.get("last_worker_denial", "") or ""
    if not reason:
        return ""
    # Act-1 Gap-07: 사유 요약 상한(120자)에서도 블록 400자 이내를 지킨다.
    reason = reason[:_DENIAL_REASON_MAX_CHARS]
    # module-6 실런(런 a217f45e) 정정: supervisor가 목록을 보고도 다른 워커의
    # description에 적힌 제한 문구를 에이전트 전체 제한으로 읽었다 — 설명의
    # 제한은 그 워커에만 적용됨을 명시한다.
    return "\n".join([
        "\n\n[워커 능력 부정 감지]",
        f"직전 워커가 자기 도구 범위를 근거로 불가를 선언했습니다: {reason}",
        "- 워커는 자기 도구 하나만 알며 에이전트 전체의 능력을 알지 못합니다.",
        "- 능력 판단은 위 '사용 가능한 워커' 목록으로만 하세요. 워커의 불가 선언과 "
        "어떤 워커 설명에 적힌 제한은 그 워커에만 적용되며, 다른 워커의 근거가 아닙니다.",
        "- 요청 기능을 가진 워커가 목록에 있으면 FINISH 대신 그 워커를 호출하세요.",
        "- 질문이 \"할 수 있는지\"를 묻는 것이면 목록 기준으로 가능함과 필요한 "
        "입력(예: 대상 번호)을 answer에 적으세요.",
        "- 목록에도 없을 때만 FINISH하고, 무엇이 불가한지 밝히세요.",
    ])


def _select_guidance_block(
    state: SupervisorState,
    wiki_worker_id: str,
    logger: LoggerInterface | None = None,
) -> tuple[str, str]:
    """안내 블록은 결정 1회에 최대 1개. 우선순위: 오류 > 빈 결과 > 능력 부정 > 재진입.

    Design Ref: worker-capability-denial-guard §4.4 (D-06). Plan SC: FR-07, FR-11.

    두 블록이 동시에 뜨면 지시가 충돌한다(early-finish-fix §6.1). supervisor_node
    본문 길이를 늘리지 않기 위해 로그까지 여기서 처리한다(Gap-05). 신호도
    pending도 없으면 ("", "") — 결정 프롬프트가 기존과 바이트 동일(FR-09).

    Returns:
        (블록 텍스트, 종류). 종류는 "error" | "empty" | "denial" | "reentry" | "".
        되물음 기회는 "empty"/"denial"에서만 세워진다 — 호출부가 종류로 분기.
    """
    block = _render_worker_error_block(state, wiki_worker_id)
    if block:
        return block, "error"
    kind = ""
    block = _render_empty_result_block(state)
    if block:
        kind = "empty"
    else:
        block = _render_capability_denial_block(state)
        kind = "denial" if block else ""
    if kind:
        if logger:
            # Plan SC: FR-11 — 되물음 기회가 세워진 시점(armed)을 남긴다.
            logger.info(
                "finish challenge armed", reason_kind=kind,
                last_worker_id=state.get("last_worker_id", ""),
            )
        return block, kind
    block = _render_challenge_reentry_block(state)
    if block:
        if logger:
            logger.info(
                "finish challenge consumed",
                reason_kind=state.get("finish_challenge_kind", ""),
            )
        return block, "reentry"
    return "", ""


# 인벤토리 항목 요약 head 절단 길이(자) — 항목당 1줄 유지 (토큰 절약).
_ENTRY_HEAD_MAX_CHARS = 80


def _entry_head(body_lines: list[str], reinjected: bool) -> str:
    """항목 요약 head — 재주입 항목은 마커 헤더 라인을 건너뛰고 실데이터에서 추출."""
    lines = body_lines[1:] if reinjected else body_lines
    for line in lines:
        if line.strip():
            return line[:_ENTRY_HEAD_MAX_CHARS]
    return ""


def _summarize_data_entry(index: int, msg) -> str:
    """검색결과 메시지 1건 → 인벤토리 요약 1줄 (본문 미포함 — 토큰 절약).

    data-inventory-requery D3: 수집 구분([이번 턴 수집]/[이전 턴 보유])과
    재주입 항목의 원 질문을 노출해 LLM의 범위 커버리지 판단 근거를 제공한다.
    """
    content = getattr(msg, "content", "")
    body_lines = content.splitlines()[1:]  # 첫 줄은 "[worker 검색결과]" 헤더
    reinjected = AnalysisSnapshotPolicy.is_reinjected(content)
    label = "[이전 턴 보유]" if reinjected else "[이번 턴 수집]"
    head = _entry_head(body_lines, reinjected)
    name = getattr(msg, "name", "")
    question = (
        AnalysisSnapshotPolicy.extract_reinjected_question(content)
        if reinjected else ""
    )
    q_part = f' 원 질문: "{question}" —' if question else ""
    return f"{index}. {label} {name} —{q_part} {head} ({len(content)}자)"


def _render_data_context_block(messages: list) -> str:
    """state 내 검색결과(현재 턴 수집분 + 재주입분) → 보유 데이터 인벤토리 블록.

    analysis-data-continuity Design §3.5 (D5): supervisor가 보유 데이터 범위를
    근거로 재사용(분석 직행) vs 재수집(검색 워커 우선)을 판단하게 한다.
    data-inventory-requery D3: 항목 순회 판단 지시로 강화. 없으면 빈 문자열.
    """
    entries = [m for m in messages if is_search_result(m)]
    if not entries:
        return ""
    lines = "\n".join(
        _summarize_data_entry(i, m) for i, m in enumerate(entries, 1)
    )
    return (
        f"\n\n[보유 분석 데이터]\n{lines}\n"
        f"- 위 목록을 항목별로 순회하며 현재 요청의 대상·기간·집단을 "
        f"보유 데이터가 커버하는지 확인하세요.\n"
        f"- 전부 커버하면 데이터 재수집 없이 분석 워커를 호출하세요.\n"
        f"- 하나라도 범위를 벗어나면(대상·기간·집단 확대 등) "
        f"먼저 검색 워커로 새 데이터를 수집한 뒤 분석 워커를 호출하세요."
    )


def _render_viz_guidance_block(
    messages: list,
    analysis_worker_ids: list[str],
    viz_policy: VisualizationRoutingPolicy | None,
) -> str:
    """시각화 요청 감지 시 supervisor decision용 인지 블록 (아니면 빈 문자열).

    차트는 분석 워커 직후 경로(chart_router → chart_builder)에서만 생성되므로,
    LLM이 검색 결과만으로 FINISH 하지 않도록 경로 제약을 명시한다.
    판단 기준은 강제 라우팅 Hook·chart_router와 동일한 도메인 정책을 공유한다.
    """
    if viz_policy is None or not analysis_worker_ids:
        return ""
    if not viz_policy.explicit_request(latest_user_question(messages)):
        return ""
    ids = ", ".join(analysis_worker_ids)
    return (
        f"\n\n[시각화 안내]\n"
        f"사용자가 그래프/차트 시각화를 요청했습니다. "
        f"차트는 분석 워커({ids})를 거쳐야만 생성됩니다.\n"
        f"외부 데이터가 필요하면 먼저 검색 워커로 데이터를 수집한 뒤, "
        f"반드시 분석 워커를 호출하세요. "
        f"검색 결과만 모은 상태에서 FINISH 하지 마세요."
    )


def _set_purpose_if_context(purpose: RunPurpose) -> None:
    """AGENT-OBS-001 §14-1: 노드 진입 시 purpose 명시.

    ContextVar에 RunContext가 없는 경우(테스트·외부 호출) 조용히 통과.
    """
    ctx = get_current_run_context()
    if ctx is not None:
        try:
            ctx.callback.set_purpose(purpose)
        except Exception:
            pass  # 관측성 실패는 본 흐름 차단 X


def build_initial_state(
    messages: list[dict],
    config: SupervisorConfig,
    available_workers: list[str],
    attachments: list[dict] | None = None,
) -> SupervisorState:
    return {
        "messages": messages,
        "iteration_count": 0,
        "max_iterations": config.max_iterations,
        "token_usage": 0,
        "token_limit": config.token_limit,
        "next_worker": "",
        "last_worker_id": "",
        "available_workers": available_workers,
        "quality_gate_enabled": config.quality_gate_enabled,
        "retry_counts": {},
        "max_retries_per_worker": config.max_retries_per_worker,
        "forced_worker": "",
        "skipped_workers": [],
        "limit_reached": False,
        "last_worker_error": "",
        # supervisor-early-finish-fix D-02 / D-05
        "last_worker_empty": "",
        # worker-capability-denial-guard D-02
        "last_worker_denial": "",
        "finish_challenge_pending": False,
        "finish_challenge_kind": "",
        "quality_gate_result": "",
        "attachments": attachments or [],
        "worker_task": "",
        "viz_decision": "",
        "charts": [],
        "visualization_done": False,
        "analysis_source": [],
    }


SUPERVISOR_TAIL_INSTRUCTION = (
    "위 대화와 워커 결과를 바탕으로 다음 행동(워커 선택 또는 FINISH)을 결정하세요."
)


class SupervisorDecision(BaseModel):
    next: str = Field(description="다음 호출할 worker_id 또는 'FINISH'")
    reasoning: str = Field(description="선택 이유")
    answer: str = Field(
        default="",
        description="FINISH 선택 시 사용자에게 전달할 응답. 워커 호출 없이 직접 답변할 때 작성.",
    )
    # worker-context-injection §3.1 (FR-04): 워커는 에이전트 프롬프트를 보지 못한다.
    # default="" — 구조화 출력이 필드를 누락해도 그래프는 기존대로 동작한다.
    task: str = Field(
        default="",
        description=(
            "선택한 워커가 지금 수행할 작업을 한국어 1~3문장으로 구체적으로 기술. "
            "대화에서 확인된 대상·기간·범위를 명시하고, 확인되지 않은 값은 "
            "지어내지 말고 '미확인'으로 남길 것. FINISH면 빈 문자열."
        ),
    )


def _challenge_reset() -> dict:
    """되물음 관련 채널 일괄 리셋 — supervisor_node의 모든 조기 return이 쓴다.

    Design Ref: worker-capability-denial-guard §4.5 (D-07). early-finish-fix
    §2.2 실측 정정: return 경로 하나라도 pending을 확정하지 않으면 route가
    supervisor로 되돌려 무한 루프가 된다. 한 곳에서 정의해 누락을 막는다.
    """
    return {
        "last_worker_empty": "",
        "last_worker_denial": "",
        "finish_challenge_pending": False,
        "finish_challenge_kind": "",
    }


def create_supervisor_node(
    llm: BaseChatModel,
    workers: list[WorkerDefinition],
    supervisor_prompt: str,
    hooks: SupervisorHooks,
    logger: LoggerInterface,
    analysis_worker_ids: list[str] | None = None,
    viz_policy: VisualizationRoutingPolicy | None = None,
    docgen_guidance_block: str = "",
    # wiki-guided-routing D3/D4: 빈 문자열이면 무영향(위키 미등록 에이전트 바이트 동일).
    wiki_guidance_block: str = "",
    wiki_worker_id: str = "",
):
    worker_descriptions = "\n".join(
        f"- {w.worker_id}: {w.description}" for w in workers
    )
    available_ids = {w.worker_id for w in workers}

    async def supervisor_node(state: SupervisorState) -> dict:
        _set_purpose_if_context(RunPurpose.SUPERVISOR)
        if state["iteration_count"] >= state["max_iterations"]:
            # agent-recursion-limit D5: 오류·침묵 종료가 아니라 조기 답변 경로로.
            # limit_reached는 라우팅(final_answer 우회)·안내 지시·payload 플래그의 신호.
            logger.warning("max_iterations reached",
                           iteration_count=state["iteration_count"])
            # supervisor-early-finish-fix D-05: 한도 가드도 되물음 기회를 명시적으로
            # 소진한다. limit_reached가 route에서 우선하므로 현재는 무해하지만,
            # 그 암묵 의존을 남기지 않는다 (§2.2 불변식).
            return {
                "next_worker": "__end__",
                "limit_reached": True,
                **_challenge_reset(),
            }

        if state["token_usage"] >= state["token_limit"]:
            logger.warning("token_limit reached",
                           token_usage=state["token_usage"])
            # supervisor-early-finish-fix D-05 (Gap-06): 이 가드는 D5 결정에 따라
            # limit_reached를 세우지 않는다(테스트로 고정). 따라서 pending이 남으면
            # route가 supervisor로 되돌리고 같은 가드가 다시 걸려 무한 루프가 된다.
            # iteration_count도 이 경로에선 증가하지 않아 한도 가드가 막지 못한다.
            return {
                "next_worker": "__end__",
                **_challenge_reset(),
            }

        forced = hooks.force_worker(state)
        if forced:
            # worker-context-injection §3.1: 강제 라우팅은 SupervisorDecision을
            # 거치지 않는다. 직전 턴의 지시가 새어 나가지 않도록 비운다.
            return {
                "next_worker": forced,
                "forced_worker": forced,
                "worker_task": "",
                "iteration_count": state["iteration_count"] + 1,
                **_challenge_reset(),
            }

        skipped = hooks.skip_workers(state)

        # 첨부 인지 블록 — supervisor가 첨부 데이터의 존재를 알게 한다.
        attachment_block = _render_attachment_block(state.get("attachments", []))
        # 보유 데이터 인지 블록 — 재사용 vs 재수집 판단 근거 (analysis-data-continuity).
        data_block = _render_data_context_block(state["messages"])
        # 시각화 인지 블록 — 차트는 분석 워커 경유 필수임을 LLM에 알린다.
        viz_block = _render_viz_guidance_block(
            state["messages"], analysis_worker_ids or [], viz_policy,
        )
        # supervisor-early-finish-fix §6.1 / worker-capability-denial-guard D-06:
        # 안내 블록은 결정 1회에 최대 1개 (오류 > 빈 결과 > 능력 부정).
        guidance_block, guidance_kind = _select_guidance_block(
            state, wiki_worker_id, logger,
        )
        # 되물음 대상은 빈 결과·능력 부정만 — 오류·재진입 블록은 제외.
        challenge_kind = guidance_kind if guidance_kind in ("empty", "denial") else ""

        decision_prompt = (
            f"{supervisor_prompt}\n\n"
            f"사용 가능한 워커:\n{worker_descriptions}"
            f"{attachment_block}"
            f"{data_block}"
            f"{viz_block}"
            # doc-generator D6: 문서 생성 라우팅 판단 기준 (빈 문자열이면 무영향)
            f"{docgen_guidance_block}"
            # wiki-guided-routing D3/D4: 위키 지침 우선 기준 + 직전 수집 실패 안내
            f"{wiki_guidance_block}"
            # D4 직전 실패 / early-finish-fix D-03 빈 결과 / denial-guard D-05 능력
            # 부정 — 배타 선택된 블록 1개. 신호 없으면 "" (바이트 동일 보존).
            f"{guidance_block}\n\n"
            f"다음 중 선택하세요:\n"
            f"- 워커 호출이 필요하면 해당 worker_id를 선택\n"
            f"- 처리 가능한 워커가 사용 가능 목록에 있으면 거부하지 말고 그 워커를 선택\n"
            f"- 권한·개인정보 보호는 각 워커의 도구가 자동으로 검증하므로, 그것을 이유로 "
            f"'FINISH'를 선택하지 마세요. 관련 정보를 찾을 가능성이 있는 워커가 있으면 "
            f"먼저 라우팅하세요\n"
            f"- 어떤 워커로도 처리할 수 없을 때만 'FINISH'를 선택하고 "
            f"answer 필드에 사용자에게 전달할 자연스러운 응답을 작성하세요\n"
            f"- 모든 작업이 완료되었으면 'FINISH'를 선택 (워커를 이미 호출했다면 "
            f"최종 답변은 시스템이 워커 결과를 종합해 생성하므로 answer는 비워두세요)\n"
            # worker-context-injection §3.1: 워커는 위 에이전트 지침을 보지
            # 못한다. task가 비면 워커는 대화 원문만 보고 작업을 재추론한다.
            f"- 워커를 선택했다면 task 필드에 그 워커가 지금 수행할 작업을 "
            f"구체적으로 적으세요. 대화에서 확인된 대상·기간·범위를 명시하고, "
            f"확인되지 않은 값은 지어내지 말고 '미확인'이라고 적으세요\n"
            f"스킵된 워커(사용 불가): {skipped}"
        )

        # fix-anthropic-prefill-error D2: 결정 프롬프트를 끝 system으로 두면
        # langchain_anthropic이 top-level system으로 끌어올려 배열이 워커
        # AIMessage로 끝남(=prefill) → Claude 4.6+ 400. system 선두 배치 +
        # assistant-last면 지시 HumanMessage를 후미에 append.
        messages = ensure_user_tail(
            [{"role": "system", "content": decision_prompt}, *state["messages"]],
            instruction=SUPERVISOR_TAIL_INSTRUCTION,
        )

        try:
            llm_with_structure = llm.with_structured_output(SupervisorDecision)
            decision = await llm_with_structure.ainvoke(messages)
            next_worker = decision.next
        except Exception as e:
            logger.error(
                "supervisor LLM decision failed, falling back to __end__",
                exception=e,
            )
            # supervisor-early-finish-fix D-05: 결정 실패는 되물음 대상이 아니다.
            # 플래그를 소진하지 않으면 route가 다시 supervisor로 돌려보내고
            # 같은 실패가 반복돼 무한 루프가 된다 (실측: 회귀 3건).
            return {
                "next_worker": "__end__",
                "last_worker_error": "",
                **_challenge_reset(),
            }

        # M3 (AGENT-OBS-003): reasoning을 step output_summary로 노출.
        # SupervisorDecision.reasoning은 이미 required 필드라 추가 LLM 토큰 비용 없음.
        step_summary = (decision.reasoning or f"next={next_worker}")[:1024]

        if next_worker == "FINISH":
            next_worker = "__end__"
            # final-answer-node DQ1: 워커가 실행된 런은 final_answer 노드가 최종 답변을
            # 생성하므로 supervisor의 draft answer를 폐기한다(이중 답변·대화 본체 오염 방지).
            if decision.answer and not state["last_worker_id"]:
                from langchain_core.messages import AIMessage
                return {
                    "next_worker": next_worker,
                    "messages": [AIMessage(content=decision.answer)],
                    "skipped_workers": skipped,
                    "worker_task": "",
                    "iteration_count": state["iteration_count"] + 1,
                    "_step_output_summary": step_summary,
                    "last_worker_error": "",
                    # supervisor-early-finish-fix D-05: 조기 return도 플래그를
                    # 소진한다 — 모든 종료 경로에서 1회 상한이 성립해야 한다.
                    **_challenge_reset(),
                }
        elif next_worker in skipped:
            next_worker = "__end__"
        elif next_worker not in available_ids and next_worker != "__end__":
            logger.warning("invalid worker selected", selected=next_worker)
            next_worker = "__end__"

        # worker-context-injection §3.1 (FR-05): 워커로 라우팅할 때만 지시를
        # 싣는다. 종료 경로에 남기면 다음 턴 워커가 낡은 지시를 받는다.
        routed_to_worker = next_worker not in ("__end__", "")
        return {
            "next_worker": next_worker,
            "skipped_workers": skipped,
            "worker_task": decision.task if routed_to_worker else "",
            "iteration_count": state["iteration_count"] + 1,
            "_step_output_summary": step_summary,
            # D4: 실패 안내 블록은 결정 1회에만 — 소비 후 리셋
            "last_worker_error": "",
            # supervisor-early-finish-fix D-02/D-05: 빈 결과 블록도 결정 1회에만.
            # 신호를 리셋하면서 되물음 기회를 세운다. 재진입 시 empty_block이
            # 비므로 pending은 False로만 갈 수 있다 — 1회 상한이 여기서 보장된다.
            "last_worker_empty": "",
            # worker-capability-denial-guard D-06/D-07: 능력 부정 신호도 소비 후
            # 리셋. pending은 두 사유 합산 — 플래그 하나로 1회 상한을 유지한다.
            "last_worker_denial": "",
            "finish_challenge_pending": bool(challenge_kind),
            # Act-1 Gap-03: 재진입 리마인더용 사유 종류 — pending과 함께 소진.
            "finish_challenge_kind": challenge_kind,
        }

    return supervisor_node


def create_quality_gate_node(
    policy: QualityGatePolicy,
    logger: LoggerInterface,
):
    async def quality_gate_node(state: SupervisorState) -> dict:
        if not state["quality_gate_enabled"]:
            return {"next_worker": "", "quality_gate_result": "skipped"}

        last_worker = state["last_worker_id"]
        messages = state["messages"]

        last_ai_msg = None
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "ai":
                last_ai_msg = msg
                break

        if last_ai_msg is None:
            return {"next_worker": "", "quality_gate_result": "skipped"}

        is_acceptable = policy.check_response(last_ai_msg.content)

        if is_acceptable:
            logger.info("quality_gate passed", worker_id=last_worker)
            return {"next_worker": "", "quality_gate_result": "passed"}

        retry_counts = dict(state["retry_counts"])
        current_retries = retry_counts.get(last_worker, 0)

        if current_retries >= state["max_retries_per_worker"]:
            logger.warning(
                "quality_gate max_retries reached, forcing pass",
                worker_id=last_worker, retries=current_retries,
            )
            return {"next_worker": "", "quality_gate_result": "max_retries"}

        retry_counts[last_worker] = current_retries + 1
        feedback_msg = {
            "role": "user",
            "content": (
                f"{QUALITY_FEEDBACK_PREFIX} 응답이 기준에 미달합니다. "
                f"더 정확하고 구체적인 답변을 다시 생성해주세요. "
                f"(재시도 {current_retries + 1}/{state['max_retries_per_worker']})"
            ),
        }

        logger.info(
            "quality_gate failed, retrying",
            worker_id=last_worker, retry=current_retries + 1,
        )

        return {
            "messages": [feedback_msg],
            "retry_counts": retry_counts,
            "next_worker": last_worker,
            "quality_gate_result": "failed",
        }

    return quality_gate_node


def route_to_worker(state: SupervisorState) -> str:
    return state["next_worker"]


def route_to_worker_or_final(state: SupervisorState) -> str:
    """depth=0 전용: FINISH 시 워커 실행 이력이 있으면 final_answer로 우회.

    final-answer-node Design §3-1 — supervisor LLM의 선택이 아닌 라우팅 함수가
    최종 답변 노드 경유를 구조적으로 보장한다. 워커 미실행(단순 대화)은 즉시 종료.

    agent-recursion-limit D6: 반복 한도 도달(limit_reached) 시에는 워커 미실행이라도
    final_answer로 우회 — 답변 없이 END 직행하는 경로를 차단한다.
    """
    next_worker = state["next_worker"]
    # approval-gate Design §2.1 ③: 승인 대기가 잡히면 즉시 종료한다.
    # final_answer 를 태우지 않는 이유 — 초안은 사람이 승인 화면에서 볼
    # 것이지 LLM 이 요약할 것이 아니고, 요약을 태우면 "완료했습니다" 같은
    # 오해 소지 문구가 나갈 수 있다. 되물음·한도보다 우선한다: 게이트가
    # 걸린 런은 더 돌 이유가 없다.
    if next_worker == "__end__" and state.get("approval_pending"):
        return "__end__"
    # supervisor-early-finish-fix D-05: 빈 결과 미해소 상태의 첫 FINISH를 1회
    # 되돌린다. 특정 워커를 강제하지 않고 재결정 기회만 준다 (그래프 계약 ③).
    # worker-capability-denial-guard D-06: 능력 부정 신호도 같은 플래그를
    # 세운다 — 두 사유 합산 1회. 종류는 finish_challenge_kind가 따로 든다.
    # D-09: 한도 도달은 되물음보다 우선 — 종료를 막지 않는다.
    # Plan SC: FR-06, FR-07
    if (
        next_worker == "__end__"
        and state.get("finish_challenge_pending")
        and not state.get("limit_reached")
    ):
        return "supervisor"
    if next_worker == "__end__" and (
        state.get("last_worker_id") or state.get("limit_reached")
    ):
        return "final_answer"
    return next_worker


def route_after_quality(state: SupervisorState) -> str:
    next_worker = state.get("next_worker", "")
    if next_worker and next_worker != "__end__":
        return next_worker
    return "supervisor"
