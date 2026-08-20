"""시스템 프롬프트 생성용 LLM 프롬프트 템플릿.

Design Ref: §4.4.

────────────────────────────────────────────────────────────────────────
§10.3 AgentComposer 와의 섹션 대조 (Plan R1 — 두 모듈이 벌어지는지 볼 기준)
비교 대상: `application/agent_composer/composer.py:_SYSTEM_PROMPT:97-102`

| 섹션      | AgentComposer            | 여기                        |
|-----------|--------------------------|-----------------------------|
| 목적      | 에이전트 목적 1~2문장     | purpose (동일)              |
| 역할      | 각 워커의 역할·사용 시점  | roles[] — **워커 비종속**   |
| 도구 지침 | 시점·호출법·주의사항      | tool_guides{when,how,caution}|
| 동작 원칙 | 실행 순서·언어·주의사항   | principles[] — 순서 제외    |
| 산출 형태 | 문자열 1개                | 구조 + 서버 조립            |

차이 2건(역할의 워커 비종속 / 원칙의 실행 순서 제외)은 **의도된 것**이다.
이 모듈은 워커·flow 개념을 모른다 (Design Q1).
────────────────────────────────────────────────────────────────────────

프롬프트의 "목록 밖 도구 금지" 지시는 **2차 방어선일 뿐**이다. 1차 방어는
`PromptAssemblyPolicy.drop_hallucinated` 가 후보 밖 tool_id 를 실제로 폐기하는
것이다 — 프롬프트만 믿지 않는다 (intent 어댑터 `_round_block` 관례).
"""

SYSTEM = (
    "당신은 AI 에이전트의 시스템 프롬프트를 설계하는 전문가입니다.\n"
    "아래 재료만으로 에이전트 프롬프트의 각 섹션을 작성하세요.\n\n"
    "{tools_block}"
    "{intent_block}"
    "[규칙]\n"
    "- purpose: 이 에이전트가 무엇을 하는지 1~2문장.\n"
    "- identity: 어떤 성격·전문성을 가진 존재이며 누구를 위해 일하는지 "
    "1~3문장. 도구가 없어도 작성합니다.\n"
    "- context.constraints: 반드시 지켜야 할 것과 하지 말아야 할 것. "
    "위 의도 블록에 제약이 있으면 **반드시 반영**하고, 목적상 당연한 것도 "
    "명시합니다. 최대 10개.\n"
    "- context.background: 이 에이전트가 전제로 알아야 할 배경. "
    "근거가 없으면 비웁니다 — 지어내지 마세요. 최대 5개.\n"
    "- roles: 에이전트가 수행하는 역할. 최대 6개. "
    "도구가 없어도 작성합니다.\n"
    "- tool_guides: **위 도구 목록에 있는 tool_id 만** 사용하세요. "
    "목록에 없는 도구를 지어내지 마세요. 각 항목에 when(언제) / "
    "how(어떤 입력으로) / caution(주의)을 씁니다.\n"
    "- workflows: 상황별 처리 절차. situation(어떤 상황인지) + "
    "steps(순서대로 할 일). 최소한 '일반 요청'과 '요청이 모호할 때' 두 상황을 "
    "포함하세요. 도구가 없어도 작성합니다. 최대 5개, 각 8단계 이내.\n"
    "- style: 응답 말투·형식·구조. 의도 블록에 말투가 있으면 그것을 따릅니다.\n"
    "- principles: 응답 언어·거절 조건·환각 금지 등 동작 원칙. "
    "판단이 충돌할 때의 우선순위가 주어졌다면 여기에 명시합니다. 최대 10개.\n"
    "- 각 섹션은 서로 다른 내용을 담습니다. 같은 문장을 여러 섹션에 "
    "반복하지 마세요.\n"
    "- 전부 한국어로 작성합니다.\n"
)

HUMAN = "{history_block}[현재 요청]\n{user_request}"

_TOOLS_TEMPLATE = "[사용 가능한 도구]\n{lines}\n\n"
_INTENT_TEMPLATE = (
    "[사전 분석된 사용자 의도]\n"
    "- 분류: {label}\n"
    "{extra}"
    "이 판정은 참고용입니다. 요청 본문과 충돌하면 요청이 우선입니다.\n\n"
)

# prompt-depth §4.4 / FR-19 — 프롬프트에 실을 슬롯 축의 **화이트리스트**.
#
# `filled_slots` 를 통째로 순회하지 않는 이유가 둘 있다:
#   ① 보안 — `IntentSnapshot` 은 `extra="allow"` 라 클라이언트 에코백으로 임의
#      키가 들어올 수 있다. 통째로 렌더하면 그것이 곧 프롬프트 인젝션 경로다.
#   ② 관측 — intent 모듈이 축을 늘릴 때마다 프롬프트가 조용히 바뀌면 생성 품질이
#      근거 없이 흔들린다. 축 추가는 여기 한 줄을 더하는 명시적 행위여야 한다.
#
# 계산 필드(complete/missing_slots/confidence)는 프롬프트 재료가 아니므로 없다.
_SLOT_LABELS: tuple[tuple[str, str], ...] = (
    ("target_users", "대상 사용자"),
    ("data_sources", "참조 자료"),
    ("tone", "말투/형식"),
    ("constraints", "지켜야 할 제약"),
    ("decision_priority", "판단 우선순위"),
)
_HISTORY_TEMPLATE = "[이전 대화]\n{lines}\n\n"


def tools_block(metas) -> str:
    """도구 목록 블록. 도구가 없으면 블록 자체를 싣지 않는다 (Design §4.4)."""
    if not metas:
        return ""
    lines = "\n".join(_tool_line(meta) for meta in metas)
    return _TOOLS_TEMPLATE.format(lines=lines)


def _tool_line(meta) -> str:
    origin = f" [{meta.server_name}]" if meta.server_name else ""
    return f"- {meta.tool_id}{origin}: {meta.name} — {meta.description}"


def intent_block(intent: dict | None) -> str:
    """의도 블록.

    FR-13 — intent 가 없거나 `degraded=true` 면 **부착하지 않는다.**
    판정 실패는 "의도 모름"이지 "의도 없음"이 아니며, 오염된 판정을 프롬프트에
    실으면 프롬프트가 왜곡된다.
    """
    if not intent or intent.get("degraded"):
        return ""
    label = str(intent.get("label") or "").strip()
    if not label:
        return ""
    reason = str(intent.get("reason") or "").strip()
    lines = [f"- 근거: {reason}"] if reason else []
    lines += _slot_lines(intent.get("filled_slots"))
    extra = "".join(f"{line}\n" for line in lines)
    return _INTENT_TEMPLATE.format(label=label, extra=extra)


def _slot_lines(filled_slots) -> list[str]:
    """선언된 축만, 값이 있는 것만 렌더한다 (§4.4)."""
    if not isinstance(filled_slots, dict):
        return []
    lines = []
    for key, caption in _SLOT_LABELS:
        value = str(filled_slots.get(key) or "").strip()
        if value:
            lines.append(f"- {caption}: {value}")
    return lines


def history_block(history: list[dict]) -> str:
    if not history:
        return ""
    lines = "\n".join(
        f"{turn.get('role', '')}: {turn.get('content', '')}" for turn in history
    )
    return _HISTORY_TEMPLATE.format(lines=lines)
